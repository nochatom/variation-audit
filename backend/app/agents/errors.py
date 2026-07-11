"""Application-level error taxonomy for LLM provider failures.

Every provider exception (litellm's, or a raw timeout) gets mapped to one of
these four before it crosses out of app/agents/reliable_llm.py — callers
(the worker, tests) only ever see these, never a raw litellm exception type,
so retry/fallback/error-code decisions don't depend on a third-party
library's exception hierarchy.
"""
from __future__ import annotations


class AIProviderError(Exception):
    """Base class for every classified LLM-provider failure."""

    code = "AI_PROVIDER_ERROR"
    retryable = False

    def __init__(self, message: str, *, provider: str | None = None, model: str | None = None):
        super().__init__(message)
        self.provider = provider
        self.model = model


class AIAuthError(AIProviderError):
    """Invalid/missing API key, or a permission-denied response (401/403).

    Never retried, never falls back — a bad key on the primary provider
    will be just as bad on the fallback's own key, and retrying burns
    latency for a failure that won't resolve itself.
    """

    code = "AI_AUTH_ERROR"
    retryable = False


class AIRateLimitError(AIProviderError):
    """429 — retried with backoff, then falls back to the secondary model."""

    code = "AI_RATE_LIMIT_ERROR"
    retryable = True


class AIProviderTimeoutError(AIProviderError):
    """Request exceeded the configured timeout (e.g. NVIDIA NIM cold start
    exceeding even a generous budget). Retried with backoff, then falls
    back."""

    code = "AI_PROVIDER_TIMEOUT"
    retryable = True


class AISchemaValidationError(AIProviderError):
    """A model's output couldn't be validated (or safely repaired) against
    its agent's output_schema — e.g. the fallback model returned a
    differently-shaped JSON object than the primary would have. Retryable:
    a fresh attempt (and eventually the fallback model) gets a chance to
    produce a conforming response, enforcing the same output contract
    across primary and fallback via the existing retry/fallback path
    rather than a separate mechanism."""

    code = "AI_SCHEMA_INVALID"
    retryable = True


class AIProviderUnavailableError(AIProviderError):
    """5xx / connection-level failure. Retried with backoff, then falls
    back. Also the default for any *unrecognized* provider exception —
    treating unknown failures as transient-and-retryable is the safer
    default than silently treating them as an unretryable auth failure."""

    code = "AI_PROVIDER_UNAVAILABLE"
    retryable = True


class NoProviderAvailableError(AIProviderError):
    """Raised by ProviderRouter.select() when zero registry candidates
    survive capability + circuit-state filtering — a clear, immediate
    failure at selection time rather than a confusing crash later inside
    ReliableLlm when it's handed nothing to work with."""

    code = "AI_NO_PROVIDER_AVAILABLE"
    retryable = False


# User-facing messages per error_code, keyed the same way AgentAnalysisJob.
# error_code is populated (app/agents/worker.py's fail_job calls). Deliberately
# generic — the raw exception text (a litellm message, or repr() of an
# unexpected exception) never crosses into a client response; it stays in
# the DB row / logs for debugging. See app/routers/agent_jobs.py's
# AgentJobOut, which uses this instead of the raw error_message column.
USER_FACING_JOB_ERROR_MESSAGES: dict[str, str] = {
    AIAuthError.code: "The AI provider rejected our credentials. Please contact support.",
    AIRateLimitError.code: "The AI provider is temporarily rate-limiting requests. Please try again shortly.",
    AIProviderTimeoutError.code: "The analysis timed out. Please try again.",
    AISchemaValidationError.code: "The AI provider returned an unexpected response. Please try again.",
    AIProviderUnavailableError.code: "The AI provider is temporarily unavailable. Please try again shortly.",
    NoProviderAvailableError.code: "No AI provider is currently available. Please try again shortly.",
    "AGENT_INTAKE_REJECTED": "This project isn't ready for analysis yet — check that a contract has been uploaded.",
    "AGENT_PIPELINE_ERROR": "Something went wrong while analyzing this project. Please try again.",
}
_DEFAULT_JOB_ERROR_MESSAGE = "Something went wrong while analyzing this project. Please try again."


def safe_job_error_message(error_code: str | None) -> str | None:
    """Maps a failed job's error_code to a safe, generic user-facing
    message — never the raw provider/exception text stored in the DB."""
    if error_code is None:
        return None
    return USER_FACING_JOB_ERROR_MESSAGES.get(error_code, _DEFAULT_JOB_ERROR_MESSAGE)


def classify_exception(exc: Exception, *, provider: str | None = None, model: str | None = None) -> AIProviderError:
    """Map a raw exception (litellm's, or a stdlib timeout) to one of the
    four AIProviderError subclasses above."""
    import litellm

    message = str(exc)
    status_code = getattr(exc, "status_code", None)

    if isinstance(exc, litellm.AuthenticationError) or status_code in (401, 403):
        return AIAuthError(message, provider=provider, model=model)

    if isinstance(exc, litellm.RateLimitError) or status_code == 429:
        return AIRateLimitError(message, provider=provider, model=model)

    if isinstance(exc, (litellm.Timeout, TimeoutError)):
        return AIProviderTimeoutError(message, provider=provider, model=model)

    if isinstance(
        exc,
        (
            litellm.ServiceUnavailableError,
            litellm.InternalServerError,
            litellm.APIConnectionError,
            litellm.APIError,
        ),
    ) or (isinstance(status_code, int) and status_code >= 500):
        return AIProviderUnavailableError(message, provider=provider, model=model)

    # Unrecognized exception type — default to retryable-unavailable rather
    # than silently blocking retries as if it were an auth failure.
    return AIProviderUnavailableError(message, provider=provider, model=model)
