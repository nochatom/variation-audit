"""Provider call telemetry: one row per completed logical provider call
(never per internal ReliableLlm retry attempt — retries stay entirely
inside ReliableLlm's own retry loop and are only ever reflected here as
metadata on the single row the eventual outcome produces), backed by
provider_call_log (migration 0012_provider_health, extended by 0013 with
retries/fallback_used for Phase 5's diagnostics metrics endpoint).

Read-time aggregation only (docs/decisions/26-provider-router.md ADR-3) —
no snapshot table, no running counters. Bounded, indexed queries against
provider_call_log compute average/p95 latency and success/failure rates
on demand.

Two distinct read paths, kept separate on purpose (Phase 5's "preserve
strict separation" requirement): get_health()/list_health() answer "is this
provider healthy enough to route to" (consumed by routing_policies.py, via
DbHealthSource — a small, routing-relevant signal). get_metrics()/
list_metrics() answer "what happened" for observability/diagnostics (a
broader set of counters, consumed only by app/routers/internal_providers.py)
— different question, different shape, not merged into one function.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.agents.provider_router_types import HealthSnapshot

DEFAULT_WINDOW = timedelta(hours=24)


def record(session: Session, metrics: dict) -> None:
    """Persist one completed call's outcome. `metrics` is the same
    consolidated dict ReliableLlm's on_llm_call sink produces (provider/
    model/input_tokens/output_tokens/latency_ms/success/error_code/
    number_of_retries/fallback_used)."""
    session.execute(
        text(
            "INSERT INTO provider_call_log "
            "(id, provider, model, selection_id, success, error_code, "
            " latency_ms, input_tokens, output_tokens, retries, fallback_used) "
            "VALUES (:id, :provider, :model, :selection_id, :success, :error_code, "
            " :latency_ms, :input_tokens, :output_tokens, :retries, :fallback_used)"
        ),
        {
            "id": str(uuid.uuid4()),
            "provider": metrics.get("provider"),
            "model": metrics.get("model"),
            "selection_id": metrics.get("selection_id"),
            "success": metrics.get("success", True),
            "error_code": metrics.get("error_code"),
            "latency_ms": metrics.get("latency_ms"),
            "input_tokens": metrics.get("input_tokens"),
            "output_tokens": metrics.get("output_tokens"),
            "retries": metrics.get("number_of_retries"),
            "fallback_used": metrics.get("fallback_used"),
        },
    )
    session.commit()


# --------------------------------------------------------------------------
# Health — routing-relevant signal (consumed by routing_policies.py)
# --------------------------------------------------------------------------
def get_health(session: Session, provider: str, window: timedelta = DEFAULT_WINDOW) -> HealthSnapshot | None:
    """Bounded, indexed (provider, created_at) aggregation — see ADR-3.
    Returns None if there's no call history for `provider` within the
    window (routing_policies.py treats that as "no data yet", not zero)."""
    row = session.execute(
        text(
            "SELECT "
            "  avg(latency_ms) AS average_latency_ms, "
            "  percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms, "
            "  avg(success::int) AS success_rate, "
            "  count(*) AS total_calls, "
            "  count(*) FILTER (WHERE NOT success) AS failure_calls "
            "FROM provider_call_log "
            "WHERE provider = :provider AND created_at > now() - :window"
        ),
        {"provider": provider, "window": window},
    ).mappings().first()

    if row is None or row["total_calls"] == 0:
        return None

    total = row["total_calls"]
    failure_rate = (row["failure_calls"] / total) if total else None
    success_rate = float(row["success_rate"]) if row["success_rate"] is not None else None

    return HealthSnapshot(
        average_latency_ms=float(row["average_latency_ms"]) if row["average_latency_ms"] is not None else None,
        p95_latency_ms=float(row["p95_latency_ms"]) if row["p95_latency_ms"] is not None else None,
        success_rate=success_rate,
        failure_rate=failure_rate,
        retry_rate=None,       # a routing-time concern only, not computed here — see get_metrics() for real retry counts
        fallback_rate=None,    # ditto — see get_metrics()
        estimated_cost_per_token=None,  # computed by whichever policy needs it, from tokens + registry price — see routing_policies.lowest_cost
        availability=success_rate,
    )


def list_health(
    session: Session, providers: list[str], window: timedelta = DEFAULT_WINDOW,
) -> dict[str, HealthSnapshot | None]:
    """get_health() for every provider in `providers` — used by
    app/routers/internal_providers.py's /health endpoint. Never called from
    routing (that's always single-provider, via DbHealthSource)."""
    return {provider: get_health(session, provider, window) for provider in providers}


# --------------------------------------------------------------------------
# Metrics — full observability/diagnostics stats (consumed only by
# app/routers/internal_providers.py, never by routing_policies.py)
# --------------------------------------------------------------------------
def get_metrics(session: Session, provider: str, window: timedelta = DEFAULT_WINDOW) -> dict:
    """Requests/successes/failures/timeouts/retries/fallbacks/latency/
    token_usage/estimated_cost for one provider, bounded to `window`."""
    row = session.execute(
        text(
            "SELECT "
            "  count(*) AS requests, "
            "  count(*) FILTER (WHERE success) AS successes, "
            "  count(*) FILTER (WHERE NOT success) AS failures, "
            "  count(*) FILTER (WHERE error_code = 'AI_PROVIDER_TIMEOUT') AS timeouts, "
            "  coalesce(sum(retries), 0) AS total_retries, "
            "  count(*) FILTER (WHERE fallback_used) AS fallbacks, "
            "  avg(latency_ms) AS average_latency_ms, "
            "  percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms, "
            "  coalesce(sum(coalesce(input_tokens, 0) + coalesce(output_tokens, 0)), 0) AS token_usage "
            "FROM provider_call_log "
            "WHERE provider = :provider AND created_at > now() - :window"
        ),
        {"provider": provider, "window": window},
    ).mappings().first()

    per_model_tokens = session.execute(
        text(
            "SELECT model, coalesce(sum(coalesce(input_tokens, 0) + coalesce(output_tokens, 0)), 0) AS tokens "
            "FROM provider_call_log "
            "WHERE provider = :provider AND created_at > now() - :window "
            "GROUP BY model"
        ),
        {"provider": provider, "window": window},
    ).mappings().all()

    estimated_cost = _estimate_cost(provider, per_model_tokens)

    requests = row["requests"] or 0 if row is not None else 0
    return {
        "requests": requests,
        "successes": (row["successes"] or 0) if row is not None else 0,
        "failures": (row["failures"] or 0) if row is not None else 0,
        "timeouts": (row["timeouts"] or 0) if row is not None else 0,
        "retries": int(row["total_retries"] or 0) if row is not None else 0,
        "fallbacks": (row["fallbacks"] or 0) if row is not None else 0,
        "average_latency_ms": float(row["average_latency_ms"]) if row and row["average_latency_ms"] is not None else None,
        "p95_latency_ms": float(row["p95_latency_ms"]) if row and row["p95_latency_ms"] is not None else None,
        "token_usage": int(row["token_usage"] or 0) if row is not None else 0,
        "estimated_cost": round(estimated_cost, 6),
    }


def list_metrics(
    session: Session, providers: list[str], window: timedelta = DEFAULT_WINDOW,
) -> dict[str, dict]:
    """get_metrics() for every provider in `providers` — used by
    app/routers/internal_providers.py's /metrics endpoint."""
    return {provider: get_metrics(session, provider, window) for provider in providers}


def _estimate_cost(provider: str, per_model_tokens) -> float:
    """Static price_per_1k_tokens (capability_registry.py) x real observed
    token usage — the rate is static config, the resulting figure is
    dynamic, per the design doc's Part 2/Part 3 split."""
    from app.agents.capability_registry import CAPABILITY_REGISTRY

    price_by_model = {
        (m.provider, m.model_name): m.price_per_1k_tokens for m in CAPABILITY_REGISTRY
    }
    total = 0.0
    for row in per_model_tokens:
        price = price_by_model.get((provider, row["model"]))
        if price:
            total += (row["tokens"] / 1000) * price
    return total


class DbHealthSource:
    """Satisfies provider_router_types.HealthSource — a drop-in for
    Phase 2's NullHealthSource, opening its own short-lived session per
    call via `session_factory` (same pattern as worker.py's heartbeat
    loop / DbCircuitBreaker above)."""

    def __init__(self, session_factory, window: timedelta = DEFAULT_WINDOW):
        self._session_factory = session_factory
        self._window = window

    def get(self, provider: str) -> HealthSnapshot | None:
        with self._session_factory() as session:
            return get_health(session, provider, window=self._window)
