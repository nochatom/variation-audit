"""Phase 1 tests (docs/decisions/26-provider-router-implementation-plan.md):
data models and registry. No selection logic yet — that's Phase 2.
"""
from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.agents.capability_registry import CAPABILITY_REGISTRY, ModelSpec
from app.agents.capability_requirements import ROLE_REQUIREMENTS
from app.agents.errors import AIProviderError, NoProviderAvailableError
from app.agents.provider_requirements import ProviderRequirements
from app.agents.provider_selection import ProviderSelection
from app.config import VALID_AGENT_ROUTING_POLICIES, Settings


# --------------------------------------------------------------------------
# ProviderRequirements / ProviderSelection — immutability + shape
# --------------------------------------------------------------------------
def test_provider_requirements_is_frozen():
    req = ProviderRequirements(capabilities=["structured_json"])
    with pytest.raises(dataclasses.FrozenInstanceError):
        req.capabilities = ["something_else"]


def test_provider_requirements_defaults():
    req = ProviderRequirements(capabilities=["structured_json"])
    assert req.min_context is None
    assert req.requires_json is False
    assert req.requires_tools is False


def test_provider_selection_is_frozen():
    sel = ProviderSelection(
        provider="nvidia_nim", model="openai/gpt-oss-120b", policy="highest_priority",
        routing_reason="test", selection_id=uuid.uuid4(), selected_at=datetime.now(timezone.utc),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        sel.provider = "other"


# --------------------------------------------------------------------------
# capability_registry.py
# --------------------------------------------------------------------------
def test_registry_phase1_seed_matches_todays_live_config():
    """Exactly one model enabled — reproduces the current
    VA_AGENT_MODEL_PROVIDER=openai runtime behavior (the Phase 4
    backward-compatibility gate's starting condition)."""
    enabled = [m for m in CAPABILITY_REGISTRY if m.enabled]
    assert len(enabled) == 1
    assert enabled[0].provider == "nvidia_nim"
    assert enabled[0].model_name == "openai/gpt-oss-120b"


def test_every_registry_entry_is_a_model_spec_with_a_price():
    for entry in CAPABILITY_REGISTRY:
        assert isinstance(entry, ModelSpec)
        assert entry.price_per_1k_tokens > 0
        assert entry.supported_capabilities  # non-empty


# --------------------------------------------------------------------------
# capability_requirements.py
# --------------------------------------------------------------------------
# The exact role strings agent_definitions.py passes to
# model_provider.get_model(role) today — a drift guard: if a role is
# renamed there without updating ROLE_REQUIREMENTS, this test catches it.
EXPECTED_ROLES = {
    "document", "contract", "variation_detection",
    "evidence", "cost_time", "report_generation", "quality_review",
}


def test_role_requirements_covers_every_agent_role():
    assert set(ROLE_REQUIREMENTS.keys()) == EXPECTED_ROLES


def test_role_requirements_match_agent_definitions_call_sites():
    import inspect

    from app.agents import agent_definitions

    source = inspect.getsource(agent_definitions)
    for role in EXPECTED_ROLES:
        assert f'get_model("{role}")' in source, f"role {role!r} not found in agent_definitions.py call sites"


def test_every_role_requirement_has_nonempty_capabilities():
    for role, req in ROLE_REQUIREMENTS.items():
        assert isinstance(req, ProviderRequirements)
        assert req.capabilities, f"{role} has no required capabilities"


# --------------------------------------------------------------------------
# config.py — fail-loud routing policy validation
# --------------------------------------------------------------------------
def test_default_routing_policy_is_valid():
    assert Settings.model_fields["agent_routing_policy"].default in VALID_AGENT_ROUTING_POLICIES


@pytest.mark.parametrize("policy", sorted(VALID_AGENT_ROUTING_POLICIES))
def test_every_valid_policy_is_accepted(monkeypatch, policy):
    monkeypatch.setenv("VA_AGENT_ROUTING_POLICY", policy)
    s = Settings(_env_file=None, jwt_secret="x" * 32)
    assert s.agent_routing_policy == policy


def test_invalid_routing_policy_raises_at_construction(monkeypatch):
    monkeypatch.setenv("VA_AGENT_ROUTING_POLICY", "made_up_policy")
    with pytest.raises(ValidationError, match="not a supported routing policy"):
        Settings(_env_file=None, jwt_secret="x" * 32)


# --------------------------------------------------------------------------
# errors.py — NoProviderAvailableError
# --------------------------------------------------------------------------
def test_no_provider_available_error_shape():
    exc = NoProviderAvailableError("nothing matched")
    assert isinstance(exc, AIProviderError)
    assert exc.code == "AI_NO_PROVIDER_AVAILABLE"
    assert exc.retryable is False
