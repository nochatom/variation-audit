"""Phase 2 tests (docs/decisions/26-provider-router-implementation-plan.md):
ProviderRouter core + routing policies. Fake/in-memory health and circuit
sources only — no database dependency introduced in this phase.
"""
from __future__ import annotations

import pytest

from app.agents.capability_registry import ModelSpec
from app.agents.errors import NoProviderAvailableError
from app.agents.provider_requirements import ProviderRequirements
from app.agents.provider_router import ProviderRouter
from app.agents.provider_router_types import HealthSnapshot
from app.agents import routing_policies


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------
class FakeHealthSource:
    def __init__(self, data: dict[str, HealthSnapshot] | None = None):
        self._data = data or {}

    def get(self, provider: str) -> HealthSnapshot | None:
        return self._data.get(provider)


class FakeCircuitSource:
    def __init__(self, open_providers: set[str] | None = None):
        self._open = open_providers or set()

    def is_open(self, provider: str) -> bool:
        return provider in self._open


def _model(provider, name, capabilities=("structured_json",), priority=5, max_context=32000,
          enabled=True, tags=(), price=0.001, supports_json=True, supports_tools=False):
    return ModelSpec(
        provider=provider, model_name=name,
        supported_capabilities=list(capabilities), max_context=max_context,
        supports_json=supports_json, supports_streaming=True, supports_reasoning=False,
        supports_tools=supports_tools, priority=priority, enabled=enabled,
        tags=list(tags), price_per_1k_tokens=price,
    )


# --------------------------------------------------------------------------
# Capability / enabled / circuit filtering
# --------------------------------------------------------------------------
def test_capability_matching_excludes_missing_capability():
    registry = [
        _model("a", "modelA", capabilities=["structured_json"]),
        _model("b", "modelB", capabilities=["summarization"]),  # missing structured_json
    ]
    router = ProviderRouter(registry=registry)
    reqs = ProviderRequirements(capabilities=["structured_json"])

    result = router.select(reqs)

    assert [s.provider for s in result] == ["a"]


def test_capability_matching_checks_min_context_and_json_and_tools():
    registry = [
        _model("small_ctx", "m1", max_context=8000),
        _model("no_json", "m2", supports_json=False),
        _model("no_tools", "m3", supports_tools=False),
        _model("qualifies", "m4", max_context=64000, supports_json=True, supports_tools=True),
    ]
    router = ProviderRouter(registry=registry)
    reqs = ProviderRequirements(
        capabilities=["structured_json"], min_context=32000, requires_json=True, requires_tools=True,
    )

    result = router.select(reqs)

    assert [s.provider for s in result] == ["qualifies"]


def test_disabled_model_is_excluded():
    registry = [
        _model("active", "m1", enabled=True),
        _model("inactive", "m2", enabled=False),
    ]
    router = ProviderRouter(registry=registry)

    result = router.select(ProviderRequirements(capabilities=["structured_json"]))

    assert [s.provider for s in result] == ["active"]


def test_open_circuit_excludes_provider():
    registry = [
        _model("healthy", "m1", priority=5),
        _model("tripped", "m2", priority=10),  # would win on priority if not excluded
    ]
    router = ProviderRouter(registry=registry, circuit_source=FakeCircuitSource({"tripped"}))

    result = router.select(ProviderRequirements(capabilities=["structured_json"]))

    assert [s.provider for s in result] == ["healthy"]


def test_no_provider_available_raises_when_everything_filtered_out():
    registry = [_model("only", "m1", capabilities=["summarization"])]
    router = ProviderRouter(registry=registry)

    with pytest.raises(NoProviderAvailableError):
        router.select(ProviderRequirements(capabilities=["structured_json"]))


def test_no_provider_available_when_all_circuits_open():
    registry = [_model("a", "m1"), _model("b", "m2")]
    router = ProviderRouter(registry=registry, circuit_source=FakeCircuitSource({"a", "b"}))

    with pytest.raises(NoProviderAvailableError):
        router.select(ProviderRequirements(capabilities=["structured_json"]))


# --------------------------------------------------------------------------
# Routing policies
# --------------------------------------------------------------------------
def test_highest_priority_routing():
    registry = [_model("low", "m1", priority=3), _model("high", "m2", priority=9)]
    router = ProviderRouter(registry=registry, policy="highest_priority")

    result = router.select(ProviderRequirements(capabilities=["structured_json"]))

    assert [s.provider for s in result] == ["high", "low"]
    assert "priority" in result[0].routing_reason


def test_lowest_latency_routing():
    registry = [_model("slow", "m1"), _model("fast", "m2")]
    health = FakeHealthSource({
        "slow": HealthSnapshot(average_latency_ms=900),
        "fast": HealthSnapshot(average_latency_ms=120),
    })
    router = ProviderRouter(registry=registry, health_source=health, policy="lowest_latency")

    result = router.select(ProviderRequirements(capabilities=["structured_json"]))

    assert [s.provider for s in result] == ["fast", "slow"]


def test_lowest_latency_ranks_unmeasured_providers_last():
    registry = [_model("unmeasured", "m1"), _model("measured", "m2")]
    health = FakeHealthSource({"measured": HealthSnapshot(average_latency_ms=500)})
    router = ProviderRouter(registry=registry, health_source=health, policy="lowest_latency")

    result = router.select(ProviderRequirements(capabilities=["structured_json"]))

    assert [s.provider for s in result] == ["measured", "unmeasured"]


def test_lowest_cost_routing_uses_observed_cost_when_available():
    registry = [
        _model("cheap_static_expensive_observed", "m1", price=0.0001),
        _model("pricier_static_cheap_observed", "m2", price=0.01),
    ]
    health = FakeHealthSource({
        "cheap_static_expensive_observed": HealthSnapshot(estimated_cost_per_token=0.05),
        "pricier_static_cheap_observed": HealthSnapshot(estimated_cost_per_token=0.001),
    })
    router = ProviderRouter(registry=registry, health_source=health, policy="lowest_cost")

    result = router.select(ProviderRequirements(capabilities=["structured_json"]))

    # observed cost (dynamic) wins over static registry price when both exist
    assert [s.provider for s in result] == ["pricier_static_cheap_observed", "cheap_static_expensive_observed"]


def test_lowest_cost_routing_falls_back_to_static_price_with_no_history():
    registry = [_model("expensive", "m1", price=0.01), _model("cheap", "m2", price=0.0001)]
    router = ProviderRouter(registry=registry, policy="lowest_cost")  # NullHealthSource default -> no history

    result = router.select(ProviderRequirements(capabilities=["structured_json"]))

    assert [s.provider for s in result] == ["cheap", "expensive"]
    assert "static price" in result[0].routing_reason


def test_highest_quality_routing_prefers_tagged_candidates():
    registry = [
        _model("plain", "m1", priority=10, tags=[]),
        _model("quality", "m2", priority=1, tags=["high_quality"]),
    ]
    router = ProviderRouter(registry=registry, policy="highest_quality")

    result = router.select(ProviderRequirements(capabilities=["structured_json"]))

    assert result[0].provider == "quality"


def test_highest_quality_routing_falls_back_when_none_tagged():
    registry = [_model("a", "m1", priority=3, tags=[]), _model("b", "m2", priority=8, tags=[])]
    router = ProviderRouter(registry=registry, policy="highest_quality")

    result = router.select(ProviderRequirements(capabilities=["structured_json"]))

    assert [s.provider for s in result] == ["b", "a"]
    assert "no high_quality-tagged candidate" in result[0].routing_reason


def test_longest_context_routing():
    registry = [_model("short", "m1", max_context=8000), _model("long", "m2", max_context=128000)]
    router = ProviderRouter(registry=registry, policy="longest_context")

    result = router.select(ProviderRequirements(capabilities=["structured_json"]))

    assert [s.provider for s in result] == ["long", "short"]


def test_unknown_policy_override_raises_loudly():
    registry = [_model("a", "m1")]
    router = ProviderRouter(registry=registry, policy="not_a_real_policy")

    with pytest.raises(ValueError, match="unknown routing policy"):
        router.select(ProviderRequirements(capabilities=["structured_json"]))


# --------------------------------------------------------------------------
# Tie-breaking
# --------------------------------------------------------------------------
def test_tiebreak_groups_equal_ranked_candidates_correctly():
    registry = [
        _model("winner", "m1", priority=10),
        _model("tied_a", "m2", priority=5),
        _model("tied_b", "m3", priority=5),
    ]
    router = ProviderRouter(registry=registry, policy="highest_priority")

    result = router.select(ProviderRequirements(capabilities=["structured_json"]))

    assert result[0].provider == "winner"
    assert {result[1].provider, result[2].provider} == {"tied_a", "tied_b"}


def test_tiebreak_actually_randomizes_across_runs(monkeypatch):
    """Not deterministic ordering — over many runs, both tied candidates
    should appear first at least once (guards against a tiebreak that
    silently always picks the same one, e.g. due to dict/list insertion
    order leaking through)."""
    seen_first = set()
    for _ in range(30):
        registry = [_model("tied_a", "m1", priority=5), _model("tied_b", "m2", priority=5)]
        router = ProviderRouter(registry=registry, policy="highest_priority")
        result = router.select(ProviderRequirements(capabilities=["structured_json"]))
        seen_first.add(result[0].provider)
        if len(seen_first) == 2:
            break

    assert seen_first == {"tied_a", "tied_b"}


# --------------------------------------------------------------------------
# POLICY_REGISTRY completeness (matches config.py's VALID_AGENT_ROUTING_POLICIES)
# --------------------------------------------------------------------------
def test_policy_registry_matches_valid_config_policies():
    from app.config import VALID_AGENT_ROUTING_POLICIES

    assert set(routing_policies.POLICY_REGISTRY.keys()) == VALID_AGENT_ROUTING_POLICIES
