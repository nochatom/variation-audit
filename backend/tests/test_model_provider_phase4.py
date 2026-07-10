"""Phase 4 tests: model_provider.py wired to ProviderRouter.

Gate 1 (backward compatibility): with VA_AGENT_ROUTING_POLICY=highest_priority
and the current registry seed, the new ProviderRouter-based selection must
produce the identical LiteLlm model/api_key/timeout the old static
agent_model_provider selection did.

Gate 3 (no healthy provider): NoProviderAvailableError must propagate from
get_model() unchanged — never silently substitute an undefined provider.
"""
from __future__ import annotations

import pytest

from app.agents import model_provider
from app.agents.errors import NoProviderAvailableError


# --------------------------------------------------------------------------
# Gate 1 — backward compatibility: old vs new selection, side by side
# --------------------------------------------------------------------------
def _old_build_litellm(provider: str, settings):
    """Reconstructs the pre-Phase-4 static selection logic exactly as it
    existed in model_provider.py before this phase, for direct comparison —
    NOT a simplification or approximation of it."""
    from google.adk.models.lite_llm import LiteLlm

    old_nvidia_nim_model_slugs = {
        "openai": "openai/gpt-oss-120b",
        "glm": "z-ai/glm-5.2",
        "gemini": "google/gemma-4-31b-it",
    }
    old_nvidia_nim_key_setting = {
        "openai": "nvidia_nim_openai_api_key",
        "glm": "nvidia_nim_glm_api_key",
        "gemini": "nvidia_nim_gemini_api_key",
    }
    old_nvidia_nim_timeout_s = {"openai": 60, "glm": 60, "gemini": 120}

    if provider in old_nvidia_nim_model_slugs:
        api_key = getattr(settings, old_nvidia_nim_key_setting[provider])
        model_slug = old_nvidia_nim_model_slugs[provider]
        timeout = old_nvidia_nim_timeout_s[provider]
        return LiteLlm(model=f"nvidia_nim/{model_slug}", api_key=api_key, timeout=timeout)

    if provider == "claude":
        return LiteLlm(model="anthropic/claude-sonnet-5", api_key=settings.anthropic_agent_api_key, timeout=60)

    raise ValueError(f"unknown provider {provider!r}")


def _old_get_model_config(settings):
    """The pre-Phase-4 get_model()'s selection decision (provider + the
    primary LiteLlm's model/api_key/timeout + whether a fallback exists),
    for comparison against the new implementation's output."""
    old_fallback_provider = "openai"
    provider = settings.agent_model_provider
    primary = _old_build_litellm(provider, settings)
    has_fallback = provider != old_fallback_provider
    return provider, primary.model, primary._additional_args, has_fallback


def test_gate1_backward_compatibility_identical_selection(monkeypatch):
    """With highest_priority policy + the current one-provider-per-role
    registry seed, old and new implementations must select the identical
    provider/model/api_key/timeout, with no fallback in either case."""
    from app.config import get_settings

    settings = get_settings()
    assert settings.agent_routing_policy == "highest_priority"
    assert settings.agent_model_provider == "openai"  # today's live config

    old_provider, old_model, old_args, old_has_fallback = _old_get_model_config(settings)

    new_llm = model_provider.get_model("document")

    assert new_llm._primary_provider == "nvidia_nim"  # the registry's actual provider id for this model
    assert new_llm._primary.model == old_model
    assert new_llm._primary._additional_args == old_args
    assert (new_llm._fallback is not None) == old_has_fallback
    assert new_llm._fallback is None  # openai is already the fallback target -> none expected


def test_gate1_every_role_resolves_without_error():
    """All 7 roles must resolve cleanly under the current registry seed —
    a broader backward-compatibility smoke test beyond the single-role
    detailed comparison above."""
    from app.agents.capability_requirements import ROLE_REQUIREMENTS

    for role in ROLE_REQUIREMENTS:
        llm = model_provider.get_model(role)
        assert llm._primary.model == "nvidia_nim/openai/gpt-oss-120b"
        assert llm._fallback is None


# --------------------------------------------------------------------------
# Gate 3 — no healthy provider -> NoProviderAvailableError propagates
# --------------------------------------------------------------------------
def test_gate3_no_provider_available_propagates_unchanged(monkeypatch):
    class _AlwaysEmptyRouter:
        def select(self, requirements):
            raise NoProviderAvailableError("no candidate survives filtering — simulated for this test")

    monkeypatch.setattr(model_provider, "_build_router", lambda: _AlwaysEmptyRouter())

    with pytest.raises(NoProviderAvailableError):
        model_provider.get_model("document")


def test_gate3_get_model_does_not_swallow_or_wrap_the_error(monkeypatch):
    """The exact exception instance/type must reach the caller — get_model()
    must not catch-and-reraise-as-something-else, and must not catch it at
    all (no silent fallback to an undefined provider)."""
    sentinel = NoProviderAvailableError("sentinel")

    class _RaisingRouter:
        def select(self, requirements):
            raise sentinel

    monkeypatch.setattr(model_provider, "_build_router", lambda: _RaisingRouter())

    with pytest.raises(NoProviderAvailableError) as excinfo:
        model_provider.get_model("contract")
    assert excinfo.value is sentinel


# --------------------------------------------------------------------------
# ProviderRouter is genuinely the active selector (not leftover static logic)
# --------------------------------------------------------------------------
def test_get_model_delegates_to_provider_router(monkeypatch):
    """Proves get_model() actually routes through ProviderRouter.select()
    rather than any static/hardcoded path — a custom selection fed in via
    a fake router must be reflected in get_model()'s output."""
    import uuid
    from datetime import datetime, timezone

    from app.agents.provider_selection import ProviderSelection

    custom_selection = ProviderSelection(
        provider="anthropic", model="claude-sonnet-5", policy="test_policy",
        routing_reason="forced by test", selection_id=uuid.uuid4(),
        selected_at=datetime.now(timezone.utc),
    )

    class _FakeRouter:
        def select(self, requirements):
            return [custom_selection]

    monkeypatch.setattr(model_provider, "_build_router", lambda: _FakeRouter())

    llm = model_provider.get_model("evidence")

    assert llm._primary_provider == "anthropic"
    assert llm._primary.model == "anthropic/claude-sonnet-5"
    assert llm._fallback is None
