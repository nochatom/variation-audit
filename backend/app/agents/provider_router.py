"""ProviderRouter — selection only (docs/decisions/26-provider-router.md §7).

Accepts a ProviderRequirements object, never an agent role string (the
router has no concept of "agent role" — see ADR-1). Never executes an LLM
call, never retries, never accesses a database directly — Phase 2 uses
in-memory fake HealthSource/CircuitSource by default; Phase 3's real,
DB-backed implementations satisfy the exact same Protocol and can be
swapped in without any change to this file.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.agents.capability_registry import CAPABILITY_REGISTRY, ModelSpec
from app.agents.errors import NoProviderAvailableError
from app.agents.provider_requirements import ProviderRequirements
from app.agents.provider_router_types import (
    AlwaysClosedCircuitSource,
    CircuitSource,
    HealthSource,
    NullHealthSource,
)
from app.agents.provider_selection import ProviderSelection
from app.agents.routing_policies import POLICY_REGISTRY


class ProviderRouter:
    def __init__(
        self,
        registry: list[ModelSpec] | None = None,
        health_source: HealthSource | None = None,
        circuit_source: CircuitSource | None = None,
        policy: str | None = None,
    ):
        self._registry = registry if registry is not None else CAPABILITY_REGISTRY
        self._health_source = health_source if health_source is not None else NullHealthSource()
        self._circuit_source = circuit_source if circuit_source is not None else AlwaysClosedCircuitSource()
        self._policy = policy  # resolved lazily in select() if None, so a later settings change is picked up

    def select(self, requirements: ProviderRequirements) -> list[ProviderSelection]:
        """Returns a ranked list (best first); the caller takes [0] as
        primary and [1] as fallback. Raises NoProviderAvailableError if no
        candidate survives filtering."""
        candidates = self._filter_by_capability(requirements)
        candidates = self._filter_by_circuit(candidates)

        if not candidates:
            raise NoProviderAvailableError(
                f"no enabled, circuit-closed provider satisfies requirements: {requirements}"
            )

        policy_name = self._resolve_policy_name()
        policy_fn = POLICY_REGISTRY[policy_name]

        health = {c.provider: self._health_source.get(c.provider) for c in candidates}
        ranked = policy_fn(candidates, health)

        now = datetime.now(timezone.utc)
        return [
            ProviderSelection(
                provider=model.provider,
                model=model.model_name,
                policy=policy_name,
                routing_reason=f"{model.provider}/{model.model_name}: {reason}",
                selection_id=uuid.uuid4(),
                selected_at=now,
            )
            for model, reason in ranked
        ]

    def _resolve_policy_name(self) -> str:
        from app.config import VALID_AGENT_ROUTING_POLICIES, get_settings

        policy_name = self._policy if self._policy is not None else get_settings().agent_routing_policy
        if policy_name not in POLICY_REGISTRY:
            # Settings() already validates this at construction time when the
            # policy comes from config — this branch only fires for an
            # explicitly-passed override, but fails just as loudly either way
            # (no silent fallback to a default policy).
            raise ValueError(
                f"unknown routing policy {policy_name!r} — expected one of "
                f"{sorted(VALID_AGENT_ROUTING_POLICIES)}"
            )
        return policy_name

    def _filter_by_capability(self, requirements: ProviderRequirements) -> list[ModelSpec]:
        required = set(requirements.capabilities)
        result = []
        for m in self._registry:
            if not m.enabled:
                continue
            if not required.issubset(m.supported_capabilities):
                continue
            if requirements.min_context is not None and m.max_context < requirements.min_context:
                continue
            if requirements.requires_json and not m.supports_json:
                continue
            if requirements.requires_tools and not m.supports_tools:
                continue
            result.append(m)
        return result

    def _filter_by_circuit(self, candidates: list[ModelSpec]) -> list[ModelSpec]:
        return [m for m in candidates if not self._circuit_source.is_open(m.provider)]
