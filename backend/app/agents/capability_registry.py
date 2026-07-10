"""Static model capability metadata — the only file to edit when adding a
new provider or model (see docs/decisions/26-provider-router.md §16/§17).

Deliberately static: nothing here changes at runtime. Dynamic health/
circuit data lives in provider_health.py / circuit_breaker.py instead
(backed by provider_call_log / provider_circuit_state) — see ADR-3/the
Part 2 vs Part 3 split in the design doc.

Phase 1 seed reproduces today's live runtime behavior exactly: only the
"openai" NVIDIA-NIM-hosted model is enabled, matching the current
VA_AGENT_MODEL_PROVIDER=openai setting — this is the "current
one-provider-per-role configuration" the Phase 4 backward-compatibility
gate is checked against (see test_model_provider_backward_compat.py).
Enabling glm/gemini/claude is a deliberate later step (flip `enabled`),
not part of this phase.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelSpec:
    provider: str                     # litellm-facing provider id, e.g. "nvidia_nim", "anthropic"
    model_name: str                   # the model slug within that provider
    supported_capabilities: list[str] = field(default_factory=list)
    max_context: int = 0
    supports_json: bool = False
    supports_streaming: bool = False
    supports_reasoning: bool = False
    supports_tools: bool = False
    priority: int = 0                 # higher wins under the highest_priority policy
    enabled: bool = False
    tags: list[str] = field(default_factory=list)
    # Static price rate — config metadata, never runtime health data (§8 of
    # the design doc). provider_health.py multiplies this against real
    # logged token counts to compute a dynamic cost aggregate; this field
    # itself never changes based on observed behavior.
    price_per_1k_tokens: float = 0.0


_ALL_TEXT_CAPABILITIES = [
    "legal_reasoning",
    "contract_analysis",
    "document_extraction",
    "citation_generation",
    "structured_json",
    "formatting",
    "multilingual",
    "summarization",
    "fast_response",
    "long_context",
]

CAPABILITY_REGISTRY: list[ModelSpec] = [
    ModelSpec(
        provider="nvidia_nim",
        model_name="openai/gpt-oss-120b",
        supported_capabilities=_ALL_TEXT_CAPABILITIES,
        max_context=128000,
        supports_json=True,
        supports_streaming=True,
        supports_reasoning=True,
        supports_tools=True,
        priority=10,
        enabled=True,
        tags=["general_purpose", "high_quality"],
        price_per_1k_tokens=0.0005,
    ),
    ModelSpec(
        provider="nvidia_nim",
        model_name="z-ai/glm-5.2",
        supported_capabilities=_ALL_TEXT_CAPABILITIES,
        max_context=128000,
        supports_json=True,
        supports_streaming=True,
        supports_reasoning=True,
        supports_tools=False,
        priority=8,
        enabled=False,  # disabled at Phase 1 seed — flip when ready to route real traffic to it
        tags=["general_purpose"],
        price_per_1k_tokens=0.0004,
    ),
    ModelSpec(
        provider="nvidia_nim",
        model_name="google/gemma-4-31b-it",
        supported_capabilities=_ALL_TEXT_CAPABILITIES,
        max_context=32000,
        supports_json=True,
        supports_streaming=True,
        supports_reasoning=False,
        supports_tools=False,
        priority=5,
        enabled=False,  # disabled at Phase 1 seed — measured 60-90s+ cold starts (see prior session's
                        # live NVIDIA NIM verification report); keep off until that's re-verified acceptable
        tags=["general_purpose"],
        price_per_1k_tokens=0.0003,
    ),
    ModelSpec(
        provider="anthropic",
        model_name="claude-sonnet-5",
        supported_capabilities=_ALL_TEXT_CAPABILITIES,
        max_context=200000,
        supports_json=True,
        supports_streaming=True,
        supports_reasoning=True,
        supports_tools=True,
        priority=9,
        enabled=False,  # no VA_ANTHROPIC_AGENT_API_KEY configured today — enable once one is
        tags=["general_purpose", "high_quality"],
        price_per_1k_tokens=0.003,
    ),
]
