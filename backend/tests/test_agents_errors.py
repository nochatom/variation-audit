"""Unit tests for app/agents/errors.py's exception classification."""
from __future__ import annotations

import litellm
import pytest

from app.agents.errors import (
    AIAuthError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    AIRateLimitError,
    classify_exception,
    safe_job_error_message,
)


def test_classifies_litellm_authentication_error():
    exc = litellm.AuthenticationError("bad key", llm_provider="nvidia_nim", model="x")
    classified = classify_exception(exc, provider="openai", model="x")
    assert isinstance(classified, AIAuthError)
    assert classified.code == "AI_AUTH_ERROR"
    assert classified.retryable is False


def test_classifies_raw_403_status_code_as_auth_error():
    class Fake403(Exception):
        status_code = 403

    classified = classify_exception(Fake403("forbidden"))
    assert isinstance(classified, AIAuthError)


def test_classifies_litellm_rate_limit_error():
    exc = litellm.RateLimitError("too many requests", llm_provider="nvidia_nim", model="x")
    classified = classify_exception(exc)
    assert isinstance(classified, AIRateLimitError)
    assert classified.code == "AI_RATE_LIMIT_ERROR"
    assert classified.retryable is True


def test_classifies_litellm_timeout():
    exc = litellm.Timeout("timed out", model="x", llm_provider="nvidia_nim")
    classified = classify_exception(exc)
    assert isinstance(classified, AIProviderTimeoutError)
    assert classified.code == "AI_PROVIDER_TIMEOUT"
    assert classified.retryable is True


def test_classifies_litellm_service_unavailable():
    exc = litellm.ServiceUnavailableError("down", llm_provider="nvidia_nim", model="x")
    classified = classify_exception(exc)
    assert isinstance(classified, AIProviderUnavailableError)
    assert classified.code == "AI_PROVIDER_UNAVAILABLE"
    assert classified.retryable is True


def test_unknown_exception_defaults_to_retryable_unavailable():
    classified = classify_exception(RuntimeError("something odd"))
    assert isinstance(classified, AIProviderUnavailableError)
    assert classified.retryable is True


@pytest.mark.parametrize("status_code", [500, 502, 503, 504])
def test_5xx_status_codes_map_to_unavailable(status_code):
    class FakeHttpError(Exception):
        pass

    exc = FakeHttpError("server error")
    exc.status_code = status_code
    classified = classify_exception(exc)
    assert isinstance(classified, AIProviderUnavailableError)


# --------------------------------------------------------------------------
# safe_job_error_message — the client-facing sanitization layer
# --------------------------------------------------------------------------
@pytest.mark.parametrize("code", [
    "AI_AUTH_ERROR", "AI_RATE_LIMIT_ERROR", "AI_PROVIDER_TIMEOUT",
    "AI_SCHEMA_INVALID", "AI_PROVIDER_UNAVAILABLE", "AI_NO_PROVIDER_AVAILABLE",
    "AGENT_INTAKE_REJECTED", "AGENT_PIPELINE_ERROR",
])
def test_safe_job_error_message_has_an_entry_for_every_known_code(code):
    message = safe_job_error_message(code)
    assert message
    assert isinstance(message, str)


def test_safe_job_error_message_none_when_no_error_code():
    assert safe_job_error_message(None) is None


def test_safe_job_error_message_falls_back_for_unknown_code():
    message = safe_job_error_message("SOME_FUTURE_CODE_NOT_YET_MAPPED")
    assert message  # never None/empty for a real (if unmapped) code


def test_safe_job_error_message_never_echoes_raw_provider_text():
    """The whole point of this function: no matter what raw exception text
    a provider or litellm produced, the safe message never contains it —
    callers must pass error_code only, never the raw message, and this
    confirms the function's signature enforces that (it doesn't even accept
    the raw message as a parameter)."""
    import inspect

    sig = inspect.signature(safe_job_error_message)
    assert list(sig.parameters) == ["error_code"]
