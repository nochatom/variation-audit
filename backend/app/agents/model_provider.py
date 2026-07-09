"""Provider-agnostic, production-reliable model resolution for the agent
scaffold.

Every LlmAgent constructor asks for a model by role via get_model() and
never hardcodes a provider — switching providers is a config change
(VA_AGENT_MODEL_PROVIDER), not a code change. What get_model() actually
returns is a ReliableLlm (app/agents/reliable_llm.py): a BaseLlm that wraps
the selected primary model with an explicit timeout, retry-with-backoff,
and fallback to a secondary NVIDIA NIM model — the NVIDIA-hosted
google/gemma-4-31b-it model measured a 60-90s+ cold-start after idle in
this session's live verification, and a bare LiteLlm has no timeout or
retry behavior of its own.

Current setup routes "openai"/"glm"/"gemini" through NVIDIA NIM's
OpenAI-compatible endpoint (build.nvidia.com) — litellm has a native
`nvidia_nim/<model-slug>` provider that resolves the endpoint itself; each
role uses its own NVIDIA API key since the three were issued separately
(see .env). "gemini" here is an NVIDIA-hosted stand-in model, not the real
Google Gemini API — there's no VA_GOOGLE_API_KEY in this project.
"claude" still goes through litellm's native Anthropic path (reads
VA_ANTHROPIC_AGENT_API_KEY), unused today but kept for a real Claude key.

Missing credentials fail at the first live model call, not at construction
time — matching this codebase's existing "unset -> feature reports
not-configured, doesn't crash" pattern (e.g. NullBillingProvider).
"""
from __future__ import annotations

from app.config import get_settings

# NVIDIA-catalog model slug per role. Defaults picked for each role's intent
# (openai -> OpenAI's open-weight gpt-oss; glm -> Z.ai's GLM; gemini ->
# Google's open-weight Gemma, the closest NVIDIA-hosted stand-in) and
# confirmed live against https://integrate.api.nvidia.com/v1/models —
# override by editing here if your NVIDIA account has a different model
# selected, or if NVIDIA retires one of these (they do this on notice; a
# retired slug fails with a clear 410 Gone at the model call, not silently).
_NVIDIA_NIM_MODEL_SLUGS = {
    "openai": "openai/gpt-oss-120b",
    "glm": "z-ai/glm-5.2",
    "gemini": "google/gemma-4-31b-it",
}

_NVIDIA_NIM_KEY_SETTING = {
    "openai": "nvidia_nim_openai_api_key",
    "glm": "nvidia_nim_glm_api_key",
    "gemini": "nvidia_nim_gemini_api_key",
}

# NVIDIA NIM request timeout, per role. gemini (gemma-4-31b-it) measured a
# genuine 60-90s+ cold start live in this session — 120s gives headroom
# above the worst observed case rather than the requirement's bare minimum.
# The other two NVIDIA-hosted roles responded in ~1-3s in the same session,
# but still get a generous timeout since cold starts are a property of
# "hasn't been called recently," not specific to one model.
_NVIDIA_NIM_TIMEOUT_S = {
    "openai": 60,
    "glm": 60,
    "gemini": 120,
}

# Fallback target for every NVIDIA-hosted role: openai/gpt-oss-120b, per the
# requirement's own example, and the fastest/most reliable of the three in
# this session's live tests. A role already ON openai has no fallback (would
# just be the same model failing twice).
_FALLBACK_PROVIDER = "openai"


def _build_litellm(provider: str) -> object:
    from google.adk.models.lite_llm import LiteLlm

    settings = get_settings()

    if provider in _NVIDIA_NIM_MODEL_SLUGS:
        api_key = getattr(settings, _NVIDIA_NIM_KEY_SETTING[provider])
        model_slug = _NVIDIA_NIM_MODEL_SLUGS[provider]
        timeout = _NVIDIA_NIM_TIMEOUT_S[provider]
        return LiteLlm(model=f"nvidia_nim/{model_slug}", api_key=api_key, timeout=timeout)

    if provider == "claude":
        return LiteLlm(model="anthropic/claude-sonnet-5", api_key=settings.anthropic_agent_api_key, timeout=60)

    raise ValueError(
        f"unknown VA_AGENT_MODEL_PROVIDER={provider!r} — expected one of "
        f"{sorted({*_NVIDIA_NIM_MODEL_SLUGS, 'claude'})}"
    )


def get_model(role: str | None = None) -> object:
    """Resolve the model to use for an agent, per VA_AGENT_MODEL_PROVIDER.

    Returns a ReliableLlm (app/agents/reliable_llm.py) wrapping the selected
    provider's LiteLlm as primary, with a fallback to NVIDIA NIM's
    openai/gpt-oss-120b for timeout/rate-limit/unavailable failures — never
    for auth failures (see app/agents/errors.py's retryable flag). `role` is
    accepted now for a future per-role override map (e.g. a cheaper model
    for Document/Contract) — unused today, every role gets the same
    provider default.
    """
    del role  # reserved for future per-role overrides
    from app.agents.reliable_llm import ReliableLlm

    provider = get_settings().agent_model_provider
    primary = _build_litellm(provider)

    fallback = None
    fallback_provider = None
    if provider != _FALLBACK_PROVIDER:
        fallback = _build_litellm(_FALLBACK_PROVIDER)
        fallback_provider = _FALLBACK_PROVIDER

    return ReliableLlm(
        primary=primary, primary_provider=provider,
        fallback=fallback, fallback_provider=fallback_provider,
    )
