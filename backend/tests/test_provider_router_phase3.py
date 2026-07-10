"""Phase 3 tests (docs/decisions/26-provider-router-implementation-plan.md):
circuit breaker state machine + health recording, against a real Postgres
(migration 0012_provider_health). Skipped automatically if no reachable
database is configured — same pattern as test_worker_integration.py.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.agents import circuit_breaker, provider_health

try:
    from app.db import engine, session_factory
    with engine.connect() as _conn:
        _conn.execute(text("SELECT 1"))
    _DB_AVAILABLE = True
except Exception:
    _DB_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _DB_AVAILABLE, reason="no reachable Postgres configured (VA_DATABASE_URL)"
)


@pytest.fixture
def provider():
    """A unique provider name per test so tests never collide, cleaned up after."""
    name = f"test-provider-{uuid.uuid4().hex[:8]}"
    yield name
    with session_factory() as session:
        session.execute(text("DELETE FROM provider_circuit_state WHERE provider = :p"), {"p": name})
        session.execute(text("DELETE FROM provider_call_log WHERE provider = :p"), {"p": name})
        session.commit()


def _fail(session, provider, error_code, threshold=3):
    circuit_breaker.record_outcome(
        session, provider, success=False, error_code=error_code, failure_threshold=threshold,
    )


# --------------------------------------------------------------------------
# Circuit breaker — state machine
# --------------------------------------------------------------------------
def test_circuit_closed_by_default(provider):
    with session_factory() as session:
        assert circuit_breaker.is_open(session, provider) is False


def test_failures_below_threshold_stay_closed(provider):
    with session_factory() as session:
        _fail(session, provider, "AI_PROVIDER_TIMEOUT", threshold=5)
        _fail(session, provider, "AI_PROVIDER_TIMEOUT", threshold=5)
        assert circuit_breaker.is_open(session, provider) is False


def test_failure_threshold_opens_circuit(provider):
    with session_factory() as session:
        for _ in range(5):
            _fail(session, provider, "AI_PROVIDER_TIMEOUT", threshold=5)
        assert circuit_breaker.is_open(session, provider) is True


def test_cooldown_transitions_open_to_half_open(provider):
    with session_factory() as session:
        for _ in range(3):
            _fail(session, provider, "AI_PROVIDER_UNAVAILABLE", threshold=3)
        assert circuit_breaker.is_open(session, provider) is True

    # simulate cooldown having elapsed by backdating opened_at directly
    with session_factory() as session:
        session.execute(
            text("UPDATE provider_circuit_state SET opened_at = :t WHERE provider = :p"),
            {"t": datetime.now(timezone.utc) - timedelta(seconds=120), "p": provider},
        )
        session.commit()

    with session_factory() as session:
        # cooldown of 60s has elapsed -> should transition to half_open and read as selectable
        assert circuit_breaker.is_open(session, provider, cooldown=timedelta(seconds=60)) is False
        row = session.execute(
            text("SELECT state FROM provider_circuit_state WHERE provider = :p"), {"p": provider}
        ).mappings().first()
        assert row["state"] == circuit_breaker.HALF_OPEN


def test_half_open_success_closes_circuit(provider):
    with session_factory() as session:
        session.execute(
            text("INSERT INTO provider_circuit_state (provider, state, failure_count) VALUES (:p, 'half_open', 5)"),
            {"p": provider},
        )
        session.commit()

    with session_factory() as session:
        circuit_breaker.record_outcome(session, provider, success=True, error_code=None)
        row = session.execute(
            text("SELECT state, failure_count FROM provider_circuit_state WHERE provider = :p"), {"p": provider}
        ).mappings().first()
        assert row["state"] == circuit_breaker.CLOSED
        assert row["failure_count"] == 0
        assert circuit_breaker.is_open(session, provider) is False


def test_half_open_failure_reopens_circuit(provider):
    with session_factory() as session:
        session.execute(
            text("INSERT INTO provider_circuit_state (provider, state, failure_count) VALUES (:p, 'half_open', 5)"),
            {"p": provider},
        )
        session.commit()

    with session_factory() as session:
        circuit_breaker.record_outcome(session, provider, success=False, error_code="AI_PROVIDER_TIMEOUT")
        row = session.execute(
            text("SELECT state FROM provider_circuit_state WHERE provider = :p"), {"p": provider}
        ).mappings().first()
        assert row["state"] == circuit_breaker.OPEN
        assert circuit_breaker.is_open(session, provider) is True


# --------------------------------------------------------------------------
# Circuit breaker — trip vs no-trip classification
# --------------------------------------------------------------------------
@pytest.mark.parametrize("error_code", ["AI_AUTH_ERROR", "AI_RATE_LIMIT_ERROR", "AI_SCHEMA_INVALID"])
def test_non_infrastructure_errors_never_trip_the_circuit(provider, error_code):
    """Covers 401/403 (both map to AI_AUTH_ERROR), 429 (AI_RATE_LIMIT_ERROR),
    and schema validation failures — none of them should move the circuit
    even after many repeats, well past any failure threshold."""
    with session_factory() as session:
        for _ in range(10):
            _fail(session, provider, error_code, threshold=3)
        assert circuit_breaker.is_open(session, provider) is False
        row = session.execute(
            text("SELECT * FROM provider_circuit_state WHERE provider = :p"), {"p": provider}
        ).mappings().first()
        assert row is None  # never even created a state row — no-op all the way through


@pytest.mark.parametrize("error_code", ["AI_PROVIDER_TIMEOUT", "AI_PROVIDER_UNAVAILABLE"])
def test_infrastructure_errors_trip_the_circuit(provider, error_code):
    with session_factory() as session:
        for _ in range(3):
            _fail(session, provider, error_code, threshold=3)
        assert circuit_breaker.is_open(session, provider) is True


def test_db_circuit_breaker_satisfies_circuit_source_protocol(provider):
    breaker = circuit_breaker.DbCircuitBreaker(session_factory)
    assert breaker.is_open(provider) is False  # no data yet -> closed/selectable


# --------------------------------------------------------------------------
# Health recording
# --------------------------------------------------------------------------
def test_health_recording_and_aggregation(provider):
    with session_factory() as session:
        provider_health.record(session, {
            "provider": provider, "model": "some-model", "success": True,
            "latency_ms": 100, "input_tokens": 10, "output_tokens": 5,
        })
        provider_health.record(session, {
            "provider": provider, "model": "some-model", "success": True,
            "latency_ms": 300, "input_tokens": 20, "output_tokens": 8,
        })
        provider_health.record(session, {
            "provider": provider, "model": "some-model", "success": False,
            "error_code": "AI_PROVIDER_TIMEOUT", "latency_ms": 5000,
        })

        snapshot = provider_health.get_health(session, provider)

    assert snapshot is not None
    assert snapshot.average_latency_ms == pytest.approx((100 + 300 + 5000) / 3, rel=0.01)
    assert snapshot.success_rate == pytest.approx(2 / 3, rel=0.01)
    assert snapshot.failure_rate == pytest.approx(1 / 3, rel=0.01)


def test_health_returns_none_when_no_history(provider):
    with session_factory() as session:
        assert provider_health.get_health(session, provider) is None


def test_db_health_source_satisfies_health_source_protocol(provider):
    with session_factory() as session:
        provider_health.record(session, {
            "provider": provider, "model": "m", "success": True, "latency_ms": 50,
        })

    source = provider_health.DbHealthSource(session_factory)
    snapshot = source.get(provider)
    assert snapshot is not None
    assert snapshot.average_latency_ms == 50
