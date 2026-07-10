"""Provider call telemetry: one row per completed logical provider call
(never per internal ReliableLlm retry attempt — retries stay entirely
inside ReliableLlm's own retry loop and are only ever reflected here as
metadata on the single row the eventual outcome produces), backed by
provider_call_log (migration 0012_provider_health).

Read-time aggregation only (docs/decisions/26-provider-router.md ADR-3) —
no snapshot table, no running counters. Bounded, indexed queries against
provider_call_log compute average/p95 latency and success/failure rates
on demand.

Not wired into anything in this phase — DbHealthSource is a drop-in for
Phase 2's NullHealthSource, available for a later integration step.
model_provider.py, worker.py, ReliableLlm, orchestrator.py, and
agent_definitions.py are all unmodified.
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
    consolidated dict ReliableLlm's on_llm_call sink already produces on
    success (provider/model/input_tokens/output_tokens/latency_ms) plus
    two fields this module also needs on the failure path — `success` and
    `error_code` — which the caller is responsible for including (see the
    Phase 3 note on ReliableLlm's current success-only sink in the
    implementation report: failure-path emission isn't wired yet, so this
    function is correct and tested, but nothing calls it with a failure
    record in production until that gap is closed)."""
    session.execute(
        text(
            "INSERT INTO provider_call_log "
            "(id, provider, model, selection_id, success, error_code, "
            " latency_ms, input_tokens, output_tokens) "
            "VALUES (:id, :provider, :model, :selection_id, :success, :error_code, "
            " :latency_ms, :input_tokens, :output_tokens)"
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
        },
    )
    session.commit()


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
        retry_rate=None,       # per-retry data isn't logged per-row (one row per logical call) — see module docstring
        fallback_rate=None,    # would need a `fallback_used` column; not added in this phase (not required by Phase 3)
        estimated_cost_per_token=None,  # computed by whichever policy needs it, from tokens + registry price — see routing_policies.lowest_cost
        availability=success_rate,
    )


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
