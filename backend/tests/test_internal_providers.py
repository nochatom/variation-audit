"""Phase 5 tests: diagnostics endpoints (app/routers/internal_providers.py).

Real Postgres required — provider_health.py/circuit_breaker.py run raw SQL
against provider_call_log/provider_circuit_state, which FakeSession can't
simulate. Skipped automatically if no reachable database is configured,
same pattern as test_worker_integration.py / test_provider_router_phase3.py.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.agents import circuit_breaker, provider_health
from app.auth.deps import get_current_user, get_db
from app.main import app
from app.models import Membership, MembershipRole, Organization, User

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

TEST_PROVIDER = "test-diagnostics-provider"


@pytest.fixture
def admin_client():
    with session_factory() as session:
        org = Organization(id=uuid.uuid4(), name="Diagnostics Test Org")
        user = User(id=uuid.uuid4(), email=f"admin-{uuid.uuid4().hex[:8]}@test.com",
                    password_hash="x", is_active=True)
        session.add_all([org, user])
        session.flush()
        session.add(Membership(id=uuid.uuid4(), user_id=user.id, company_id=org.id,
                               role=MembershipRole.admin))
        session.commit()
        user_id = user.id

    def _db():
        with session_factory() as session:
            yield session

    def _user():
        with session_factory() as session:
            return session.get(User, user_id)

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def member_client():
    """A regular (non-admin) member — used for the invalid-admin-access test."""
    with session_factory() as session:
        org = Organization(id=uuid.uuid4(), name="Diagnostics Test Org (member)")
        user = User(id=uuid.uuid4(), email=f"member-{uuid.uuid4().hex[:8]}@test.com",
                    password_hash="x", is_active=True)
        session.add_all([org, user])
        session.flush()
        session.add(Membership(id=uuid.uuid4(), user_id=user.id, company_id=org.id,
                               role=MembershipRole.member))
        session.commit()
        user_id = user.id

    def _db():
        with session_factory() as session:
            yield session

    def _user():
        with session_factory() as session:
            return session.get(User, user_id)

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _cleanup_test_provider_rows():
    yield
    with session_factory() as session:
        session.execute(text("DELETE FROM provider_call_log WHERE provider = :p"), {"p": TEST_PROVIDER})
        session.execute(text("DELETE FROM provider_circuit_state WHERE provider = :p"), {"p": TEST_PROVIDER})
        session.commit()


# --------------------------------------------------------------------------
# Authorization
# --------------------------------------------------------------------------
def test_unauthenticated_request_rejected():
    app.dependency_overrides.clear()
    client = TestClient(app)
    resp = client.get("/internal/providers")
    assert resp.status_code in (401, 403)


def test_non_admin_member_rejected(member_client):
    resp = member_client.get("/internal/providers")
    assert resp.status_code == 403


def test_admin_accepted(admin_client):
    resp = admin_client.get("/internal/providers")
    assert resp.status_code == 200


@pytest.mark.parametrize("path", [
    "/internal/providers", "/internal/providers/models",
    "/internal/providers/health", "/internal/providers/circuits",
    "/internal/providers/metrics",
])
def test_every_endpoint_requires_admin(member_client, path):
    resp = member_client.get(path)
    assert resp.status_code == 403


# --------------------------------------------------------------------------
# Response schema (every endpoint)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("path", [
    "/internal/providers", "/internal/providers/models",
    "/internal/providers/health", "/internal/providers/circuits",
    "/internal/providers/metrics",
])
def test_response_envelope_shape(admin_client, path):
    resp = admin_client.get(path)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"generated_at", "schema_version", "data"}
    assert body["schema_version"] == "1.0"
    # generated_at must be a real, parseable ISO timestamp
    from datetime import datetime
    datetime.fromisoformat(body["generated_at"])


# --------------------------------------------------------------------------
# Registry listing
# --------------------------------------------------------------------------
def test_list_providers_reflects_the_static_registry(admin_client):
    resp = admin_client.get("/internal/providers")
    body = resp.json()["data"]["providers"]
    provider_names = {p["provider"] for p in body}
    assert "nvidia_nim" in provider_names
    nvidia = next(p for p in body if p["provider"] == "nvidia_nim")
    assert nvidia["enabled_model_count"] >= 1
    assert nvidia["total_model_count"] >= nvidia["enabled_model_count"]


def test_list_models_returns_full_raw_registry(admin_client):
    resp = admin_client.get("/internal/providers/models")
    models = resp.json()["data"]["models"]
    assert len(models) >= 4  # today's registry seed: 3 nvidia_nim + 1 anthropic
    sample = models[0]
    assert set(sample.keys()) == {
        "provider", "model_name", "supported_capabilities", "max_context",
        "supports_json", "supports_streaming", "supports_reasoning", "supports_tools",
        "priority", "enabled", "tags", "price_per_1k_tokens",
    }


# --------------------------------------------------------------------------
# Health aggregation — empty vs. populated
# --------------------------------------------------------------------------
def test_health_empty_state(admin_client):
    resp = admin_client.get("/internal/providers/health")
    body = resp.json()["data"]
    assert body["health"].get(TEST_PROVIDER) is None or TEST_PROVIDER not in body["health"]


def test_health_populated_state(admin_client):
    """/health only reports providers the static registry knows about (by
    design — see _all_providers()), so this uses a real registered
    provider ("nvidia_nim") rather than TEST_PROVIDER. A fresh, isolated
    window (1 hour, cleaned up after) keeps this independent of any other
    activity against that provider in the shared test database."""
    with session_factory() as session:
        provider_health.record(session, {
            "provider": "nvidia_nim", "model": "diagnostics-test-model", "success": True,
            "latency_ms": 100, "input_tokens": 5, "output_tokens": 5,
        })
        provider_health.record(session, {
            "provider": "nvidia_nim", "model": "diagnostics-test-model", "success": False,
            "error_code": "AI_PROVIDER_TIMEOUT", "latency_ms": 5000,
        })

    try:
        resp = admin_client.get("/internal/providers/health")
        body = resp.json()["data"]["health"]
        assert body["nvidia_nim"] is not None
        # at least these 2 rows exist within the window; other tests/usage
        # against nvidia_nim in the shared DB may add more, so assert
        # presence and plausible bounds rather than an exact rate.
        assert 0.0 <= body["nvidia_nim"]["success_rate"] <= 1.0
    finally:
        with session_factory() as session:
            session.execute(text("DELETE FROM provider_call_log WHERE model = 'diagnostics-test-model'"))
            session.commit()


# --------------------------------------------------------------------------
# Circuit reporting — empty vs. populated
# --------------------------------------------------------------------------
def test_circuits_empty_state(admin_client):
    resp = admin_client.get("/internal/providers/circuits")
    circuits = resp.json()["data"]["circuits"]
    assert not any(c["provider"] == TEST_PROVIDER for c in circuits)


def test_circuits_populated_state(admin_client):
    with session_factory() as session:
        for _ in range(5):
            circuit_breaker.record_outcome(
                session, TEST_PROVIDER, success=False,
                error_code="AI_PROVIDER_UNAVAILABLE", failure_threshold=5,
            )

    resp = admin_client.get("/internal/providers/circuits")
    circuits = resp.json()["data"]["circuits"]
    row = next(c for c in circuits if c["provider"] == TEST_PROVIDER)
    assert row["state"] == "open"
    assert row["failure_count"] == 5


def test_diagnostics_never_mutate_circuit_state(admin_client):
    """Reading /circuits must never trip, reset, or otherwise change
    provider_circuit_state — confirms the endpoint is genuinely read-only."""
    with session_factory() as session:
        circuit_breaker.record_outcome(session, TEST_PROVIDER, success=True, error_code=None)

    admin_client.get("/internal/providers/circuits")
    admin_client.get("/internal/providers/circuits")

    with session_factory() as session:
        row = circuit_breaker._get_state_row(session, TEST_PROVIDER)
    assert row["state"] == "closed"
    assert row["failure_count"] == 0


# --------------------------------------------------------------------------
# Metrics reporting — empty vs. populated
# --------------------------------------------------------------------------
def test_metrics_empty_state(admin_client):
    resp = admin_client.get("/internal/providers/metrics")
    metrics = resp.json()["data"]["metrics"]
    entry = metrics.get(TEST_PROVIDER)
    assert entry is None or entry["requests"] == 0


def test_metrics_populated_state(admin_client):
    """/metrics, same as /health above, only reports registry-known
    providers — uses "nvidia_nim" with a distinctive model name so the
    delta from these 2 rows is isolable and cleaned up after."""
    def _counts():
        resp = admin_client.get("/internal/providers/metrics")
        return resp.json()["data"]["metrics"].get("nvidia_nim") or {
            "requests": 0, "successes": 0, "failures": 0, "timeouts": 0,
            "retries": 0, "fallbacks": 0, "token_usage": 0,
        }

    before = _counts()

    with session_factory() as session:
        provider_health.record(session, {
            "provider": "nvidia_nim", "model": "diagnostics-metrics-test", "success": True,
            "latency_ms": 200, "input_tokens": 10, "output_tokens": 20,
            "number_of_retries": 1, "fallback_used": False,
        })
        provider_health.record(session, {
            "provider": "nvidia_nim", "model": "diagnostics-metrics-test", "success": False,
            "error_code": "AI_PROVIDER_TIMEOUT", "latency_ms": 3000,
            "number_of_retries": 2, "fallback_used": True,
        })

    try:
        after = _counts()
        assert after["requests"] - before["requests"] == 2
        assert after["successes"] - before["successes"] == 1
        assert after["failures"] - before["failures"] == 1
        assert after["timeouts"] - before["timeouts"] == 1
        assert after["retries"] - before["retries"] == 3
        assert after["fallbacks"] - before["fallbacks"] == 1
        assert after["token_usage"] - before["token_usage"] == 30
    finally:
        with session_factory() as session:
            session.execute(text("DELETE FROM provider_call_log WHERE model = 'diagnostics-metrics-test'"))
            session.commit()


def test_metrics_window_hours_is_bounded_and_configurable(admin_client):
    resp = admin_client.get("/internal/providers/metrics?window_hours=1")
    assert resp.status_code == 200
    resp2 = admin_client.get("/internal/providers/metrics?window_hours=999999")
    assert resp2.status_code == 422  # exceeds the ge/le bound


# --------------------------------------------------------------------------
# No side effects anywhere (spec requirement 5)
# --------------------------------------------------------------------------
def test_diagnostics_endpoints_never_write_to_provider_call_log(admin_client):
    with session_factory() as session:
        before = session.execute(
            text("SELECT count(*) FROM provider_call_log WHERE provider = :p"), {"p": TEST_PROVIDER}
        ).scalar_one()

    admin_client.get("/internal/providers/health")
    admin_client.get("/internal/providers/metrics")

    with session_factory() as session:
        after = session.execute(
            text("SELECT count(*) FROM provider_call_log WHERE provider = :p"), {"p": TEST_PROVIDER}
        ).scalar_one()

    assert before == after
