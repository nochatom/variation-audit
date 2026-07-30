"""Tests for Production Hardening Pass 2 — Security Hardening.

Covers the concrete fixes made in this pass:
- global request body size cap (app/body_size_limit.py)
- CSV register row-count DoS guard (app/parsing.py)
- LocalDocumentLoader path-traversal guard (app/storage.py)
- logout/logout-all now rate-limited (app/auth/router.py)
- cross-tenant IDOR checks (regression proof, not new behavior — the audit
  for this pass found these already correctly enforced; these tests make
  that claim independently verifiable rather than relying on manual review)
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app import parsing
from app.auth.deps import get_current_user, get_db
from app.body_size_limit import MaxBodySizeMiddleware
from app.main import app
from app.models import Membership, MembershipRole, Project, ProjectStatus, User, Variation
from tests.fakes import FakeResult, FakeSession


# --------------------------------------------------------------------------
# Global body size cap
# --------------------------------------------------------------------------
@pytest.fixture
def capped_client():
    micro = FastAPI()
    micro.add_middleware(MaxBodySizeMiddleware, max_bytes=1000)

    @micro.post("/echo")
    async def echo(request: Request):
        body = await request.body()
        return {"len": len(body)}

    return TestClient(micro)


def test_body_within_cap_passes_through(capped_client):
    resp = capped_client.post("/echo", content=b"x" * 100)
    assert resp.status_code == 200
    assert resp.json() == {"len": 100}


def test_body_exceeding_cap_with_honest_content_length_rejected(capped_client):
    resp = capped_client.post("/echo", content=b"x" * 2000)
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_body_exceeding_cap_with_no_content_length_still_rejected(capped_client):
    """The real attack this guards against: a client that omits or lies
    about Content-Length and just streams past the cap."""
    def gen():
        for _ in range(30):
            yield b"x" * 100  # 3000 bytes, no Content-Length header sent

    resp = capped_client.post("/echo", content=gen())
    assert resp.status_code == 413


def test_body_exactly_at_cap_is_allowed(capped_client):
    resp = capped_client.post("/echo", content=b"x" * 1000)
    assert resp.status_code == 200


def test_normal_get_request_unaffected():
    """Sanity check against the real app — the global cap must not break
    ordinary traffic."""
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200


# --------------------------------------------------------------------------
# CSV register row-count guard
# --------------------------------------------------------------------------
def _rfi_csv_with_rows(n: int) -> bytes:
    lines = ["subject,question"]
    lines += [f"s{i},q{i}" for i in range(n)]
    return ("\n".join(lines) + "\n").encode()


def test_csv_under_row_limit_parses_normally():
    rows = parsing.parse_rfi_csv(_rfi_csv_with_rows(10))
    assert len(rows) == 10


def test_csv_over_row_limit_rejected():
    with pytest.raises(parsing.CsvTooManyRows):
        parsing.parse_rfi_csv(_rfi_csv_with_rows(parsing.MAX_CSV_ROWS + 1))


@pytest.mark.parametrize("parse_fn,header", [
    (parsing.parse_rfi_csv, "subject,question"),
    (parsing.parse_site_instructions_csv, "instruction"),
    (parsing.parse_meeting_minutes_csv, "topic"),
    (parsing.parse_comms_csv, "text"),
])
def test_every_csv_parser_enforces_the_row_cap(parse_fn, header):
    lines = [header] + [",".join(["x"] * header.count(",") + ["x"]) for _ in range(parsing.MAX_CSV_ROWS + 1)]
    data = ("\n".join(lines) + "\n").encode()
    with pytest.raises(parsing.CsvTooManyRows):
        parse_fn(data)


def test_oversized_csv_upload_endpoint_returns_400_not_500():
    """End-to-end: the row-count guard surfaces as a clean 400 through the
    existing _parse_or_400 catch-all, never an unhandled 500."""
    user = User(id=uuid.uuid4(), email="ca@firm.com", password_hash="x", is_active=True)
    cid = uuid.uuid4()
    project = Project(id=uuid.uuid4(), company_id=cid, name="Tower A", status=ProjectStatus.in_progress)
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid)
    session = FakeSession(results=[FakeResult(scalars=[membership])], get_obj=project)

    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        client = TestClient(app)
        big_csv = _rfi_csv_with_rows(parsing.MAX_CSV_ROWS + 1)
        resp = client.post(f"/projects/{project.id}/rfis",
                           files={"file": ("rfis.csv", big_csv, "text/csv")})
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# LocalDocumentLoader path-traversal guard
# --------------------------------------------------------------------------
def test_local_loader_rejects_parent_traversal_key(tmp_path):
    from app.storage import LocalDocumentLoader

    loader = LocalDocumentLoader(str(tmp_path))
    with pytest.raises(ValueError):
        loader.load("../../../../etc/passwd")
    with pytest.raises(ValueError):
        loader.put("../../escape.txt", "data")
    with pytest.raises(ValueError):
        loader.delete("../escape.txt")


def test_local_loader_rejects_absolute_path_key(tmp_path):
    from app.storage import LocalDocumentLoader
    import os

    loader = LocalDocumentLoader(str(tmp_path))
    absolute = os.path.abspath(os.sep) + "etc" + os.sep + "passwd" if os.name != "nt" else "C:\\Windows\\System32\\config"
    with pytest.raises(ValueError):
        loader.load(absolute)


def test_local_loader_normal_key_still_works(tmp_path):
    """The guard must not break legitimate server-generated keys."""
    from app.storage import LocalDocumentLoader

    loader = LocalDocumentLoader(str(tmp_path))
    key = f"{uuid.uuid4()}/{uuid.uuid4()}/docs/{uuid.uuid4()}.txt"
    loader.put(key, "hello world")
    assert loader.load(key) == "hello world"
    loader.delete(key)


# --------------------------------------------------------------------------
# logout / logout-all rate limiting
# --------------------------------------------------------------------------
def test_logout_endpoint_is_rate_limited():
    from app.rate_limit import limiter

    limiter.reset()
    client = TestClient(app)
    statuses = []
    for _ in range(10):
        resp = client.post("/auth/logout", json={"refresh_token": "not-a-real-token"})
        statuses.append(resp.status_code)
    assert 429 in statuses, f"expected a 429 among {statuses} — logout has no rate limit?"
    limiter.reset()


# --------------------------------------------------------------------------
# Cross-tenant IDOR — independent proof, not just manual review
# --------------------------------------------------------------------------
def test_project_from_a_different_company_returns_404_not_the_project():
    """A well-formed project_id belonging to a company the caller is NOT a
    member of must 404, never leak the project."""
    user = User(id=uuid.uuid4(), email="attacker@evil.com", password_hash="x", is_active=True)
    my_company = uuid.uuid4()
    my_membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=my_company)

    other_company = uuid.uuid4()
    victim_project = Project(id=uuid.uuid4(), company_id=other_company, name="Secret Project",
                             status=ProjectStatus.in_progress)

    session = FakeSession(results=[FakeResult(scalars=[my_membership])], get_obj=victim_project)
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        client = TestClient(app)
        resp = client.get(f"/projects/{victim_project.id}")
        assert resp.status_code == 404
        assert "Secret Project" not in resp.text
    finally:
        app.dependency_overrides.clear()


def test_variation_from_a_different_company_is_forbidden():
    """A well-formed variation_id belonging to a different company must be
    rejected — the variation content must never reach the response body."""
    user = User(id=uuid.uuid4(), email="attacker@evil.com", password_hash="x", is_active=True)
    other_company = uuid.uuid4()
    victim_variation = Variation(
        id=uuid.uuid4(), company_id=other_company, project_id=uuid.uuid4(),
        title="Confidential Variation - $500k claim",
    )

    session = FakeSession(results=[FakeResult(scalar=None)], get_obj=victim_variation)
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        client = TestClient(app)
        resp = client.get(f"/variations/{victim_variation.id}")
        assert resp.status_code == 403
        assert "500k" not in resp.text
        assert "Confidential" not in resp.text
    finally:
        app.dependency_overrides.clear()


def test_unauthenticated_request_to_protected_endpoint_rejected():
    app.dependency_overrides.clear()
    client = TestClient(app)
    resp = client.get(f"/projects/{uuid.uuid4()}")
    assert resp.status_code in (401, 403)


def test_non_admin_cannot_reach_admin_only_endpoint():
    user = User(id=uuid.uuid4(), email="member@firm.com", password_hash="x", is_active=True)
    cid = uuid.uuid4()
    member_row = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid,
                            role=MembershipRole.member)
    session = FakeSession(results=[FakeResult(scalar=member_row)])
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        client = TestClient(app)
        resp = client.get(f"/orgs/{cid}/members")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_jwt_secret_strength_validation(monkeypatch):
    """Enforce that settings fail to load if VA_JWT_SECRET is weak."""
    from pydantic import ValidationError
    from app.config import Settings, get_settings

    # Clear cache so we can construct fresh Settings
    get_settings.cache_clear()

    # 1. Test weak key
    monkeypatch.setenv("VA_JWT_SECRET", "weakkey")
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "VA_JWT_SECRET is too weak" in str(exc_info.value)

    # 2. Test strong key (>= 32 characters)
    monkeypatch.setenv("VA_JWT_SECRET", "this-is-a-strong-jwt-secret-key-32-chars-long")
    settings = Settings()
    assert settings.jwt_secret == "this-is-a-strong-jwt-secret-key-32-chars-long"

    get_settings.cache_clear()


# --------------------------------------------------------------------------
# Multi-org Admin require_any_org_admin tests
# --------------------------------------------------------------------------
def test_require_any_org_admin_with_multiple_admin_memberships():
    """Verify that require_any_org_admin allows users who are admins of
    multiple organizations to authenticate without throwing MultipleResultsFound."""
    from app.auth.deps import require_any_org_admin

    user = User(id=uuid.uuid4(), email="admin@multi.com", password_hash="x", is_active=True)
    cid1 = uuid.uuid4()
    cid2 = uuid.uuid4()
    admin_m1 = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid1, role=MembershipRole.admin)
    admin_m2 = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid2, role=MembershipRole.admin)

    session = FakeSession(results=[FakeResult(scalars=[admin_m1, admin_m2])])

    res = require_any_org_admin(user=user, session=session)
    assert res == user


def test_require_any_org_admin_endpoint_with_multiple_admin_memberships():
    """Verify through TestClient that multi-org admins can successfully access
    endpoints protected by require_any_org_admin (like /internal/storage/health)."""
    user = User(id=uuid.uuid4(), email="admin@multi.com", password_hash="x", is_active=True)
    cid1 = uuid.uuid4()
    cid2 = uuid.uuid4()
    admin_m1 = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid1, role=MembershipRole.admin)
    admin_m2 = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid2, role=MembershipRole.admin)

    session = FakeSession(results=[FakeResult(scalars=[admin_m1, admin_m2])])
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        client = TestClient(app)
        resp = client.get("/internal/storage/health")
        # Should not crash with 500, but succeed (e.g., 200)
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.clear()
