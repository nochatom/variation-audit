"""OWASP hardening: input validation limits, upload size caps, rate limiting."""
import uuid

from fastapi.testclient import TestClient

from app.auth.deps import get_current_user, get_db
from app.main import app
from app.models import Membership, Project, ProjectStatus, User
from app.rate_limit import limiter
from app.storage import get_store
from tests.fakes import FakeResult, FakeSession


class FakeStore:
    def put(self, key, data):
        return key


def _project_client():
    user = User(id=uuid.uuid4(), email="ca@firm.com", password_hash="x", is_active=True)
    cid = uuid.uuid4()
    project = Project(id=uuid.uuid4(), company_id=cid, name="Tower A",
                      status=ProjectStatus.in_progress)
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid)
    # scalar= satisfies ensure_member's scalar_one_or_none(); scalars= satisfies
    # _load_project's scalars().all() — different endpoints use different queries.
    session = FakeSession(results=[FakeResult(scalar=membership, scalars=[membership])],
                          get_obj=project)

    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_store] = lambda: FakeStore()
    return TestClient(app), project


def teardown_function():
    app.dependency_overrides.clear()


# -- upload size cap ---------------------------------------------------------
def test_oversized_rfi_csv_upload_rejected():
    client, project = _project_client()
    oversized = b"a" * (11 * 1024 * 1024)  # 11MB > 10MB cap; content need not parse
    resp = client.post(f"/projects/{project.id}/rfis", files={"file": ("rfis.csv", oversized, "text/csv")})
    assert resp.status_code == 413


# -- project input validation -------------------------------------------------
def test_create_project_rejects_invalid_state():
    client, _ = _project_client()
    resp = client.post("/projects", json={
        "company_id": str(uuid.uuid4()), "name": "Tower A", "state": "XX",
    })
    assert resp.status_code == 422


def test_create_project_rejects_blank_name():
    client, _ = _project_client()
    resp = client.post("/projects", json={"company_id": str(uuid.uuid4()), "name": "   "})
    assert resp.status_code == 422


def test_create_project_accepts_valid_au_state(monkeypatch):
    client, project = _project_client()
    created = Project(id=uuid.uuid4(), company_id=project.company_id, name="Tower A",
                      state="VIC", status=ProjectStatus.in_progress)
    import app.services.projects as project_service
    monkeypatch.setattr(project_service, "create_project", lambda *a, **k: created)
    resp = client.post("/projects", json={
        "company_id": str(project.company_id), "name": "Tower A", "state": "vic",
    })
    assert resp.status_code == 201
    assert resp.json()["state"] == "VIC"


# -- comment validation --------------------------------------------------------
def _variation_client():
    user = User(id=uuid.uuid4(), email="ca@firm.com", password_hash="x", is_active=True)
    session = FakeSession(get_obj=None)  # not reached — validation fails first

    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_add_comment_rejects_blank_body():
    v = uuid.UUID(int=1)
    resp = _variation_client().post(f"/variations/{v}/comments", json={"body": "   "})
    assert resp.status_code == 422


def test_add_comment_rejects_oversized_body():
    v = uuid.UUID(int=1)
    resp = _variation_client().post(f"/variations/{v}/comments", json={"body": "x" * 5001})
    assert resp.status_code == 422


# -- auth password policy ------------------------------------------------------
def test_signup_rejects_short_password():
    session = FakeSession(results=[FakeResult(scalar=None)])

    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    resp = TestClient(app).post("/auth/signup", json={
        "email": "new@firm.com.au", "password": "short", "org_name": "Acme",
    })
    assert resp.status_code == 422


# -- rate limiting --------------------------------------------------------------
def test_login_rate_limited_after_5_attempts():
    limiter.reset()  # isolate from other tests' auth-endpoint calls
    try:
        session = FakeSession(results=[FakeResult(scalar=None)])

        def _db():
            yield session
        app.dependency_overrides[get_db] = _db
        client = TestClient(app)
        payload = {"email": "nope@firm.com", "password": "wrong1234"}
        statuses = [client.post("/auth/login", json=payload).status_code for _ in range(6)]
        assert statuses[:5] == [401, 401, 401, 401, 401]  # invalid creds, but allowed through
        assert statuses[5] == 429                          # 6th request in the same minute: rate-limited
    finally:
        limiter.reset()
