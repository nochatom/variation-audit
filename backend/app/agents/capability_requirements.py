"""Role -> ProviderRequirements static map (docs/decisions/26-provider-router.md
§5, ADR-2). Plain data, no per-agent classes — every entry has the
identical shape, so this is homogeneous configuration, not behavior.

model_provider.py's only interaction with this module is a dict lookup by
role. Agents themselves never see this — agent_definitions.py and the
orchestrator are unmodified by this file's existence.
"""
from __future__ import annotations

from app.agents.provider_requirements import ProviderRequirements

ROLE_REQUIREMENTS: dict[str, ProviderRequirements] = {
    # Keys match the exact role strings agent_definitions.py already passes
    # to model_provider.get_model(role) today — "document", not
    # "document_agent" (that longer form is the ADK agent *name*, a
    # different namespace used only for orchestrator progress tracking).
    "document": ProviderRequirements(
        capabilities=["document_extraction", "summarization"],
        requires_json=True,
    ),
    "contract": ProviderRequirements(
        capabilities=["contract_analysis", "long_context"],
        min_context=32000,
        requires_json=True,
    ),
    "variation_detection": ProviderRequirements(
        capabilities=["legal_reasoning", "contract_analysis", "structured_json"],
        min_context=32000,
        requires_json=True,
    ),
    "evidence": ProviderRequirements(
        capabilities=["citation_generation", "structured_json"],
        requires_json=True,
    ),
    "cost_time": ProviderRequirements(
        capabilities=["structured_json", "fast_response"],
        requires_json=True,
    ),
    "report_generation": ProviderRequirements(
        capabilities=["formatting", "summarization", "long_context"],
        min_context=32000,
    ),
    "quality_review": ProviderRequirements(
        capabilities=["structured_json", "legal_reasoning"],
        requires_json=True,
    ),
}
