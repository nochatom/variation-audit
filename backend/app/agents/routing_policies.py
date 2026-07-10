"""Routing policy strategies (docs/decisions/26-provider-router.md §10).

Each policy is a pure function: `(candidates, health) -> list[tuple[ModelSpec, str]]`,
best-first, where the string is a short human-readable fragment describing
why that candidate ranked where it did. ProviderRouter (provider_router.py)
wraps each pair into a full ProviderSelection — policies never construct
one directly, so they don't need to know about selection_id/selected_at/
the policy name.

Tie-breaking (design doc §7 step 4 — random shuffle among equally-ranked
candidates) happens inside each policy via _rank_with_tiebreak: candidates
sharing the same rank key are shuffled among themselves before being
flattened back into one ordered list, so the router doesn't need to
introspect an opaque ranking to find ties itself.
"""
from __future__ import annotations

import random
from collections.abc import Callable

from app.agents.capability_registry import ModelSpec
from app.agents.provider_router_types import HealthSnapshot

Policy = Callable[[list[ModelSpec], dict[str, HealthSnapshot]], list[tuple[ModelSpec, str]]]


def _rank_with_tiebreak(
    candidates: list[ModelSpec],
    key_fn: Callable[[ModelSpec], object],
    reason_fn: Callable[[ModelSpec], str],
    reverse: bool = False,
) -> list[tuple[ModelSpec, str]]:
    """Groups candidates by key_fn's value, shuffles within each equal-key
    group (load-balancing tiebreak), then flattens groups in rank order."""
    grouped: dict[object, list[ModelSpec]] = {}
    for c in candidates:
        grouped.setdefault(key_fn(c), []).append(c)

    ordered_keys = sorted(grouped.keys(), reverse=reverse)
    result: list[tuple[ModelSpec, str]] = []
    for key in ordered_keys:
        group = grouped[key]
        random.shuffle(group)
        result.extend((c, reason_fn(c)) for c in group)
    return result


def highest_priority(candidates: list[ModelSpec], health: dict[str, HealthSnapshot]) -> list[tuple[ModelSpec, str]]:
    del health  # not used by this policy
    return _rank_with_tiebreak(
        candidates,
        key_fn=lambda m: m.priority,
        reason_fn=lambda m: f"highest configured priority ({m.priority})",
        reverse=True,
    )


def lowest_latency(candidates: list[ModelSpec], health: dict[str, HealthSnapshot]) -> list[tuple[ModelSpec, str]]:
    def latency_of(m: ModelSpec) -> float:
        snapshot = health.get(m.provider)
        if snapshot is None or snapshot.average_latency_ms is None:
            return float("inf")  # no data yet -> ranked last, never preferred over a measured provider
        return snapshot.average_latency_ms

    def reason(m: ModelSpec) -> str:
        snapshot = health.get(m.provider)
        if snapshot is None or snapshot.average_latency_ms is None:
            return "no latency data yet"
        return f"lowest observed average latency ({snapshot.average_latency_ms:.0f}ms)"

    return _rank_with_tiebreak(candidates, key_fn=latency_of, reason_fn=reason, reverse=False)


def lowest_cost(candidates: list[ModelSpec], health: dict[str, HealthSnapshot]) -> list[tuple[ModelSpec, str]]:
    def cost_of(m: ModelSpec) -> float:
        snapshot = health.get(m.provider)
        if snapshot is not None and snapshot.estimated_cost_per_token is not None:
            return snapshot.estimated_cost_per_token
        # No observed history yet — fall back to the static registry rate
        # (design doc §10: "falling back to registry price alone if a
        # provider has no call history yet").
        return m.price_per_1k_tokens / 1000

    def reason(m: ModelSpec) -> str:
        snapshot = health.get(m.provider)
        if snapshot is not None and snapshot.estimated_cost_per_token is not None:
            return f"lowest observed cost/token (${snapshot.estimated_cost_per_token:.6f})"
        return f"lowest static price (${m.price_per_1k_tokens}/1k tokens, no usage history yet)"

    return _rank_with_tiebreak(candidates, key_fn=cost_of, reason_fn=reason, reverse=False)


def highest_quality(candidates: list[ModelSpec], health: dict[str, HealthSnapshot]) -> list[tuple[ModelSpec, str]]:
    del health
    tagged = [m for m in candidates if "high_quality" in m.tags]
    pool = tagged if tagged else candidates
    fallback_note = "" if tagged else " (no high_quality-tagged candidate available; ranked from all candidates)"

    return _rank_with_tiebreak(
        pool,
        key_fn=lambda m: m.priority,
        reason_fn=lambda m: f"highest priority among high-quality models ({m.priority}){fallback_note}",
        reverse=True,
    )


def longest_context(candidates: list[ModelSpec], health: dict[str, HealthSnapshot]) -> list[tuple[ModelSpec, str]]:
    del health
    return _rank_with_tiebreak(
        candidates,
        key_fn=lambda m: m.max_context,
        reason_fn=lambda m: f"longest context window ({m.max_context} tokens)",
        reverse=True,
    )


POLICY_REGISTRY: dict[str, Policy] = {
    "highest_priority": highest_priority,
    "lowest_latency": lowest_latency,
    "lowest_cost": lowest_cost,
    "highest_quality": highest_quality,
    "longest_context": longest_context,
}
