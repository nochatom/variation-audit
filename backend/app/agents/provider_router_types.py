"""Shared types for the Provider Router's dependencies on dynamic health/
circuit data — split into their own module so routing_policies.py and
provider_router.py can both depend on them without a circular import.

Phase 2 (this module + provider_router.py + routing_policies.py) only ever
sees these as abstract interfaces, satisfied by simple in-memory fakes in
tests. Phase 3 implements the real, DB-backed HealthSource/CircuitSource
(provider_health.py, circuit_breaker.py) satisfying the same shape —
structural typing (Protocol), so Phase 3 needs no import from this module
at all, just matching method signatures.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class HealthSnapshot:
    """Dynamic, observed data for one provider — never static registry
    metadata (docs/decisions/26-provider-router.md §8's Part 2/Part 3
    split). All fields optional: a provider with no call history yet has
    no observed data, which routing_policies.py handles explicitly rather
    than treating as zero/best-case."""

    average_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    success_rate: float | None = None
    failure_rate: float | None = None
    retry_rate: float | None = None
    fallback_rate: float | None = None
    estimated_cost_per_token: float | None = None
    availability: float | None = None


class HealthSource(Protocol):
    def get(self, provider: str) -> HealthSnapshot | None:
        """Return the current health snapshot for `provider`, or None if
        there's no observed data yet."""
        ...


class CircuitSource(Protocol):
    def is_open(self, provider: str) -> bool:
        """Return True if `provider`'s circuit is currently OPEN (should
        be excluded from selection)."""
        ...


class NullHealthSource:
    """No observed data for any provider — every routing policy falls back
    to its own no-data behavior (e.g. lowest_cost falls back to static
    registry price). The Phase 2 default so ProviderRouter is usable
    stand-alone before Phase 3's real health tracking exists."""

    def get(self, provider: str) -> HealthSnapshot | None:
        del provider
        return None


class AlwaysClosedCircuitSource:
    """Every provider's circuit reads as closed — the Phase 2 default so
    ProviderRouter is usable stand-alone before Phase 3's real circuit
    breaker persistence exists."""

    def is_open(self, provider: str) -> bool:
        del provider
        return False
