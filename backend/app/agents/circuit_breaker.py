"""Per-provider circuit breaker (docs/decisions/26-provider-router.md §9),
backed by provider_circuit_state (migration 0012_provider_health).

State machine:
    CLOSED --[N consecutive trip-worthy failures]--> OPEN
    OPEN --[cooldown elapses]--> HALF_OPEN (checked lazily, on the next
                                             is_open() read — same lazy-
                                             transition style as
                                             services/billing.py's grace
                                             period expiry check)
    HALF_OPEN --[next call succeeds]--> CLOSED
    HALF_OPEN --[next call fails]--> OPEN (cooldown restarts)

Trip-worthy failure codes: AI_PROVIDER_TIMEOUT, AI_PROVIDER_UNAVAILABLE
(errors.py's AIProviderTimeoutError / AIProviderUnavailableError). NOT
trip-worthy: AI_AUTH_ERROR (401/403), AI_SCHEMA_INVALID, AI_RATE_LIMIT_ERROR
(429) — none of these indicate the provider is unreachable, so none of them
touch circuit state at all, not even failure_count/last_failure. 429 is
still fully recorded in provider_call_log (see provider_health.py) and
handled by ReliableLlm's own retry/backoff — it simply never reaches this
module's state machine.

This module implements the CircuitSource Protocol (provider_router_types.py)
via DbCircuitBreaker — a drop-in replacement for Phase 2's
AlwaysClosedCircuitSource, not wired into ProviderRouter's default anywhere
in this phase. ProviderRouter, model_provider.py, worker.py, orchestrator.py,
and agent_definitions.py are all unmodified.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"

# Only these two error codes ever affect circuit state — see module
# docstring. Deliberately a small explicit set, not "anything not in an
# allowlist," so a new AIProviderError subclass added later defaults to
# NOT tripping the circuit unless someone deliberately adds its code here.
TRIPPING_ERROR_CODES = frozenset({"AI_PROVIDER_TIMEOUT", "AI_PROVIDER_UNAVAILABLE"})

DEFAULT_FAILURE_THRESHOLD = 5
DEFAULT_COOLDOWN = timedelta(seconds=60)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_state_row(session: Session, provider: str) -> dict | None:
    row = session.execute(
        text(
            "SELECT provider, state, failure_count, opened_at, last_success, last_failure "
            "FROM provider_circuit_state WHERE provider = :provider"
        ),
        {"provider": provider},
    ).mappings().first()
    return dict(row) if row is not None else None


def _upsert_state(session: Session, provider: str, **fields) -> None:
    existing = _get_state_row(session, provider)
    if existing is None:
        columns = ["provider", *fields.keys()]
        params = {"provider": provider, **fields}
        placeholders = ", ".join(f":{c}" for c in columns)
        session.execute(
            text(f"INSERT INTO provider_circuit_state ({', '.join(columns)}) VALUES ({placeholders})"),
            params,
        )
    else:
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        session.execute(
            text(f"UPDATE provider_circuit_state SET {set_clause} WHERE provider = :provider"),
            {"provider": provider, **fields},
        )


def is_open(
    session: Session, provider: str, cooldown: timedelta = DEFAULT_COOLDOWN,
) -> bool:
    """Whether `provider` should currently be excluded from selection.

    HALF_OPEN reads as NOT open (i.e. selectable) — that's the point of
    the half-open trial. The lazy OPEN -> HALF_OPEN transition (once
    cooldown has elapsed) is persisted here, on read, matching this
    codebase's existing lazy-expiry-check pattern (see
    services/billing.py's grace-period handling).
    """
    row = _get_state_row(session, provider)
    if row is None or row["state"] == CLOSED:
        return False
    if row["state"] == HALF_OPEN:
        return False
    # state == OPEN
    opened_at = row["opened_at"]
    if opened_at is not None and _now() - _as_aware(opened_at) >= cooldown:
        _upsert_state(session, provider, state=HALF_OPEN)
        session.commit()
        return False
    return True


def record_outcome(
    session: Session,
    provider: str,
    *,
    success: bool,
    error_code: str | None,
    failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
) -> None:
    """Update circuit state for one completed logical call (not per
    internal ReliableLlm retry attempt — one call in, one state update).

    Non-trip-worthy failures (auth, schema validation, rate limit) are a
    deliberate no-op here — they don't touch failure_count, last_failure,
    or the state machine at all, so they can never accumulate toward
    tripping a circuit that's specifically about infrastructure
    availability.
    """
    now = _now()

    if success:
        # Any success — from CLOSED, HALF_OPEN, or even a stray OPEN read —
        # resets the failure count and closes the circuit if it wasn't
        # already closed.
        _upsert_state(
            session, provider,
            state=CLOSED, failure_count=0, last_success=now,
            opened_at=None,
        )
        session.commit()
        return

    if error_code not in TRIPPING_ERROR_CODES:
        return  # not an infrastructure failure — circuit state untouched

    row = _get_state_row(session, provider)
    current_state = row["state"] if row else CLOSED
    failure_count = (row["failure_count"] if row else 0) + 1

    if current_state == HALF_OPEN:
        # Failed its trial — back to OPEN, cooldown restarts.
        _upsert_state(session, provider, state=OPEN, failure_count=failure_count,
                      opened_at=now, last_failure=now)
    elif failure_count >= failure_threshold:
        _upsert_state(session, provider, state=OPEN, failure_count=failure_count,
                      opened_at=now, last_failure=now)
    else:
        _upsert_state(session, provider, failure_count=failure_count, last_failure=now)

    session.commit()


def _as_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class DbCircuitBreaker:
    """Satisfies provider_router_types.CircuitSource — a drop-in for
    Phase 2's AlwaysClosedCircuitSource, opening its own short-lived
    session per call via `session_factory` (same pattern as worker.py's
    heartbeat loop — never shares a session with whatever's making the
    LLM call)."""

    def __init__(self, session_factory, cooldown: timedelta = DEFAULT_COOLDOWN):
        self._session_factory = session_factory
        self._cooldown = cooldown

    def is_open(self, provider: str) -> bool:
        with self._session_factory() as session:
            return is_open(session, provider, cooldown=self._cooldown)
