"""Provider Router diagnostics — read-only, admin-only
(docs/decisions/26-provider-router.md §11, Phase 5).

Architecture: this router NEVER queries a database table directly. Every
endpoint calls into exactly one of the existing services —
app.agents.capability_registry (Provider Registry, static, no DB),
app.agents.provider_health (Provider Health / Metrics), or
app.agents.circuit_breaker (Circuit Breaker) — which own the storage
access. Strict separation is preserved between all four concerns; no
function here bridges two of them.

No endpoint here can execute provider selection, call an LLM, or change any
provider/circuit/metrics state — every service function called is a pure
read. Confirm this by inspection: nothing in this file imports
ProviderRouter, ReliableLlm, or any `record`/`record_outcome`/`_upsert_state`
write path.

Auth: every endpoint requires the caller to be an admin of at least one
organization (app.auth.deps.require_admin is org-scoped and doesn't fit —
this data is platform-wide infrastructure state, not any one org's data,
and this codebase has no separate "platform admin" role to reuse instead;
requiring org-admin-of-any-org is the closest fit to "the existing admin
authorization mechanism" without inventing a new role).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import circuit_breaker, provider_health
from app.agents.capability_registry import CAPABILITY_REGISTRY
from app.auth.deps import get_current_user, get_db
from app.models import Membership, MembershipRole, User

router = APIRouter(prefix="/internal/providers", tags=["internal-providers"])

SCHEMA_VERSION = "1.0"


def _require_any_org_admin(
    user: User = Depends(get_current_user), session: Session = Depends(get_db),
) -> User:
    """Admin of at least one organization — see module docstring for why
    this differs from the usual org-scoped require_admin."""
    is_admin = session.execute(
        select(Membership).where(
            Membership.user_id == user.id, Membership.role == MembershipRole.admin,
        )
    ).scalar_one_or_none()
    if is_admin is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin role required")
    return user


def _envelope(data) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": SCHEMA_VERSION,
        "data": data,
    }


def _all_providers() -> list[str]:
    """Distinct provider ids from the static registry — the Provider
    Registry is the single source of truth for "what providers exist" that
    the other three endpoints iterate over."""
    seen: list[str] = []
    for model in CAPABILITY_REGISTRY:
        if model.provider not in seen:
            seen.append(model.provider)
    return seen


# --------------------------------------------------------------------------
# Provider Registry
# --------------------------------------------------------------------------
@router.get("")
def list_providers(_admin: User = Depends(_require_any_org_admin)) -> dict:
    """Provider-level summary from the static registry (no DB)."""
    providers = []
    for provider in _all_providers():
        models = [m for m in CAPABILITY_REGISTRY if m.provider == provider]
        providers.append({
            "provider": provider,
            "total_model_count": len(models),
            "enabled_model_count": sum(1 for m in models if m.enabled),
        })
    return _envelope({"providers": providers})


@router.get("/models")
def list_models(_admin: User = Depends(_require_any_org_admin)) -> dict:
    """Full raw capability registry — every ModelSpec field, every model,
    enabled or not (no DB)."""
    models = [
        {
            "provider": m.provider,
            "model_name": m.model_name,
            "supported_capabilities": m.supported_capabilities,
            "max_context": m.max_context,
            "supports_json": m.supports_json,
            "supports_streaming": m.supports_streaming,
            "supports_reasoning": m.supports_reasoning,
            "supports_tools": m.supports_tools,
            "priority": m.priority,
            "enabled": m.enabled,
            "tags": m.tags,
            "price_per_1k_tokens": m.price_per_1k_tokens,
        }
        for m in CAPABILITY_REGISTRY
    ]
    return _envelope({"models": models})


# --------------------------------------------------------------------------
# Provider Health
# --------------------------------------------------------------------------
@router.get("/health")
def get_health(
    window_hours: int = Query(default=24, ge=1, le=24 * 30),
    _admin: User = Depends(_require_any_org_admin),
    session: Session = Depends(get_db),
) -> dict:
    """Per-provider routing-relevant health aggregates (average/p95
    latency, success/failure rate, availability) — via
    app.agents.provider_health.list_health(), never raw SQL here."""
    snapshots = provider_health.list_health(session, _all_providers(), window=timedelta(hours=window_hours))
    health = {
        provider: (
            {
                "average_latency_ms": s.average_latency_ms,
                "p95_latency_ms": s.p95_latency_ms,
                "success_rate": s.success_rate,
                "failure_rate": s.failure_rate,
                "availability": s.availability,
            }
            if s is not None else None
        )
        for provider, s in snapshots.items()
    }
    return _envelope({"window_hours": window_hours, "health": health})


# --------------------------------------------------------------------------
# Circuit Breaker
# --------------------------------------------------------------------------
@router.get("/circuits")
def get_circuits(
    _admin: User = Depends(_require_any_org_admin),
    session: Session = Depends(get_db),
) -> dict:
    """Every provider_circuit_state row, via
    app.agents.circuit_breaker.list_states() — read-only, never triggers
    the lazy OPEN->HALF_OPEN transition (that only happens on an actual
    selection attempt's is_open() call, not here)."""
    states = circuit_breaker.list_states(session)
    circuits = [
        {
            "provider": row["provider"],
            "state": row["state"],
            "failure_count": row["failure_count"],
            "opened_at": row["opened_at"].isoformat() if row["opened_at"] else None,
            "last_success": row["last_success"].isoformat() if row["last_success"] else None,
            "last_failure": row["last_failure"].isoformat() if row["last_failure"] else None,
        }
        for row in states
    ]
    return _envelope({"circuits": circuits})


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------
@router.get("/metrics")
def get_metrics(
    window_hours: int = Query(default=24, ge=1, le=24 * 30),
    _admin: User = Depends(_require_any_org_admin),
    session: Session = Depends(get_db),
) -> dict:
    """Requests/successes/failures/timeouts/retries/fallbacks/latency/
    token_usage/estimated_cost per provider, via
    app.agents.provider_health.list_metrics() — distinct from /health
    above (routing-relevant signal) even though both read
    provider_call_log; see provider_health.py's module docstring."""
    metrics = provider_health.list_metrics(session, _all_providers(), window=timedelta(hours=window_hours))
    return _envelope({"window_hours": window_hours, "metrics": metrics})
