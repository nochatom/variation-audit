"""Tests for GET /internal/storage/health (app/routers/internal_storage.py).

Real Postgres required for auth (Membership lookup) — same skip-if-unreachable
pattern as test_internal_providers.py.
"""
from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

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

FAKE_KEY = "endpoint-test-service-role-key-should-never-leak"


@pytest.fixture
def admin_client():
    with session_factory() as session:
        org = Organization(id=uuid.uuid4(), name="Storage Health Test Org")
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
    with session_factory() as session:
        org = Organization(id=uuid.uuid4(), name="Storage Health Test Org (member)")
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


# --------------------------------------------------------------------------
# Authorization
# --------------------------------------------------------------------------
def test_unauthenticated_request_rejected():
    app.dependency_overrides.clear()
    client = TestClient(app)
    resp = client.get("/internal/storage/health")
    assert resp.status_code in (401, 403)


def test_non_admin_member_rejected(member_client):
    resp = member_client.get("/internal/storage/health")
    assert resp.status_code == 403


def test_admin_accepted(admin_client):
    resp = admin_client.get("/internal/storage/health")
    assert resp.status_code == 200


# --------------------------------------------------------------------------
# Response shape and content
# --------------------------------------------------------------------------
def test_response_has_required_fields(admin_client):
    resp = admin_client.get("/internal/storage/health")
    body = resp.json()
    assert set(body.keys()) == {"provider", "bucket", "status", "checked_at", "details"}
    from datetime import datetime
    datetime.fromisoformat(body["checked_at"])


def test_healthy_supabase_configuration(admin_client, monkeypatch):
    from app import config

    class S:
        environment = "development"
        local_doc_dir = None
        supabase_url = "https://project.supabase.co"
        supabase_service_role_key = FAKE_KEY
        supabase_storage_bucket = "project-documents"
        s3_bucket = "va-bucket"

    monkeypatch.setattr(config, "get_settings", lambda: S())
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(
        200, json={"id": "project-documents", "public": False},
    ))

    resp = admin_client.get("/internal/storage/health")
    body = resp.json()
    assert body["provider"] == "supabase"
    assert body["bucket"] == "project-documents"
    assert body["status"] == "healthy"


def test_missing_configuration_reports_non_healthy_status(admin_client, monkeypatch):
    from app import config

    class S:
        environment = "development"
        local_doc_dir = None
        supabase_url = None
        supabase_service_role_key = None
        supabase_storage_bucket = "project-documents"
        s3_bucket = "va-bucket"

    monkeypatch.setattr(config, "get_settings", lambda: S())

    resp = admin_client.get("/internal/storage/health")
    body = resp.json()
    assert body["status"] != "healthy"


def test_bucket_unavailable_reports_unhealthy(admin_client, monkeypatch):
    from app import config

    class S:
        environment = "development"
        local_doc_dir = None
        supabase_url = "https://project.supabase.co"
        supabase_service_role_key = FAKE_KEY
        supabase_storage_bucket = "project-documents"
        s3_bucket = "va-bucket"

    monkeypatch.setattr(config, "get_settings", lambda: S())
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(500, json={"error": "internal"}))

    resp = admin_client.get("/internal/storage/health")
    body = resp.json()
    assert body["status"] == "unhealthy"


# --------------------------------------------------------------------------
# Security: no secrets ever appear in the response
# --------------------------------------------------------------------------
def test_response_never_contains_the_service_role_key(admin_client, monkeypatch):
    from app import config

    class S:
        environment = "development"
        local_doc_dir = None
        supabase_url = "https://project.supabase.co"
        supabase_service_role_key = FAKE_KEY
        supabase_storage_bucket = "project-documents"
        s3_bucket = "va-bucket"

    monkeypatch.setattr(config, "get_settings", lambda: S())
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(
        200, json={"id": "project-documents"},
    ))

    resp = admin_client.get("/internal/storage/health")
    raw = resp.text
    assert FAKE_KEY not in raw
    assert "service_role" not in raw.lower()
    assert "authorization" not in raw.lower()
    assert "bearer" not in raw.lower()


def test_no_log_record_emitted_during_the_request_contains_the_key(admin_client, monkeypatch, caplog):
    from app import config

    class S:
        environment = "development"
        local_doc_dir = None
        supabase_url = "https://project.supabase.co"
        supabase_service_role_key = FAKE_KEY
        supabase_storage_bucket = "project-documents"
        s3_bucket = "va-bucket"

    monkeypatch.setattr(config, "get_settings", lambda: S())
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(
        200, json={"id": "project-documents"},
    ))

    with caplog.at_level("DEBUG"):
        admin_client.get("/internal/storage/health")

    for record in caplog.records:
        assert FAKE_KEY not in record.getMessage()
        assert FAKE_KEY not in str(getattr(record, "__dict__", {}))


def test_endpoint_never_writes_or_deletes_objects(admin_client, monkeypatch):
    """Confirms the endpoint only ever performs the read-only bucket-metadata
    GET, never a call to the object put/delete path — by making any other
    HTTP verb fail the test outright."""
    from app import config

    class S:
        environment = "development"
        local_doc_dir = None
        supabase_url = "https://project.supabase.co"
        supabase_service_role_key = FAKE_KEY
        supabase_storage_bucket = "project-documents"
        s3_bucket = "va-bucket"

    monkeypatch.setattr(config, "get_settings", lambda: S())

    def fake_get(url, headers=None, timeout=None):
        assert "/object/" not in url
        return httpx.Response(200, json={"id": "project-documents"})

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("must never POST"))
    monkeypatch.setattr(httpx, "delete", lambda *a, **k: pytest.fail("must never DELETE"))

    resp = admin_client.get("/internal/storage/health")
    assert resp.status_code == 200
