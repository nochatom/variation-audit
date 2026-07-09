"""Auth (.2): security, tokens, service, and endpoints (no Postgres)."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth import service
from app.auth.deps import get_db
from app.auth.security import hash_password, verify_password
from app.auth.tokens import TokenError, create_access_token, decode_token
from app.main import app
from app.models import MembershipRole, Organization, User
from tests.fakes import FakeResult, FakeSession


# -- security --------------------------------------------------------------
def test_password_hash_roundtrip():
    h = hash_password("s3cret-pw")
    assert h != "s3cret-pw"               # never store plaintext
    assert verify_password("s3cret-pw", h)
    assert not verify_password("wrong", h)


# -- tokens ----------------------------------------------------------------
def test_token_roundtrip():
    uid = str(uuid.uuid4())
    tok = create_access_token(uid, extra={"email": "a@b.co"})
    payload = decode_token(tok)
    assert payload["sub"] == uid
    assert payload["email"] == "a@b.co"


def test_token_tampered_rejected():
    tok = create_access_token("u1")
    with pytest.raises(TokenError):
        decode_token(tok + "x")


# -- service ---------------------------------------------------------------
def test_signup_creates_user_org_admin_membership():
    session = FakeSession(results=[FakeResult(scalar=None)])   # email not taken
    user, org, m = service.signup(
        session, email="ca@firm.com.au", password="pw12345",
        full_name="Casey A", org_name="Acme Builders",
    )
    assert isinstance(user, User) and isinstance(org, Organization)
    assert user.password_hash and user.password_hash != "pw12345"
    assert m.role == MembershipRole.admin
    assert m.user_id == user.id and m.company_id == org.id   # explicit-uuid FK linkage
    assert session.commits == 1


def test_signup_duplicate_email_raises():
    existing = User(id=uuid.uuid4(), email="dupe@firm.com", password_hash="x")
    session = FakeSession(results=[FakeResult(scalar=existing)])
    with pytest.raises(service.EmailAlreadyExists):
        service.signup(session, email="dupe@firm.com", password="pw",
                       full_name=None, org_name="Org")


def test_authenticate_success_and_failure():
    user = User(id=uuid.uuid4(), email="x@y.co", password_hash=hash_password("right"),
                is_active=True)
    ok = FakeSession(results=[FakeResult(scalar=user)])
    assert service.authenticate(ok, email="x@y.co", password="right") is user
    bad = FakeSession(results=[FakeResult(scalar=user)])
    assert service.authenticate(bad, email="x@y.co", password="wrong") is None


def test_authenticate_fails_closed_for_passwordless_account():
    """An account with no local password (e.g. provisioned via a future SSO
    integration) must never authenticate via the password endpoint — this
    must fail closed, not crash or fall through to a truthy comparison."""
    user = User(id=uuid.uuid4(), email="sso@y.co", password_hash=None, is_active=True)
    session = FakeSession(results=[FakeResult(scalar=user)])
    assert service.authenticate(session, email="sso@y.co", password="anything") is None


# -- endpoints (TestClient + get_db override) ------------------------------
def _client_with(session) -> TestClient:
    def _override_db():
        yield session
    app.dependency_overrides[get_db] = _override_db
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_health():
    assert TestClient(app).get("/health").json()["status"] == "ok"


def test_signup_endpoint_is_non_enumerating():
    """Signup must return an IDENTICAL response whether the email is new or
    already registered — the old 201-with-tokens vs 409 split was a
    deterministic user-enumeration oracle. The frontend now follows signup
    with a normal login to obtain tokens."""
    fresh = _client_with(FakeSession(results=[FakeResult(scalar=None)]))
    r_new = fresh.post("/auth/signup", json={
        "email": "new@firm.com.au", "password": "pw123456", "org_name": "Acme"})
    assert r_new.status_code == 202
    assert "message" in r_new.json()
    assert "access_token" not in r_new.json()
    app.dependency_overrides.clear()

    existing = User(id=uuid.uuid4(), email="new@firm.com.au",
                    password_hash=hash_password("other"), is_active=True)
    dup = _client_with(FakeSession(results=[FakeResult(scalar=existing)]))
    r_dup = dup.post("/auth/signup", json={
        "email": "new@firm.com.au", "password": "pw123456", "org_name": "Acme"})
    assert r_dup.status_code == r_new.status_code
    assert r_dup.json() == r_new.json()   # byte-identical body, no oracle


def test_signup_existing_email_creates_no_account():
    existing = User(id=uuid.uuid4(), email="taken@firm.com",
                    password_hash=hash_password("pw"), is_active=True)
    session = FakeSession(results=[FakeResult(scalar=existing)])
    client = _client_with(session)
    client.post("/auth/signup", json={
        "email": "taken@firm.com", "password": "pw123456", "org_name": "Acme"})
    assert session.added_of(User) == []   # nothing written for the duplicate


def test_login_endpoint_success_and_bad_password():
    user = User(id=uuid.uuid4(), email="l@firm.com", password_hash=hash_password("good"),
                is_active=True)
    ok = _client_with(FakeSession(results=[FakeResult(scalar=user)]))
    assert ok.post("/auth/login", json={"email": "l@firm.com", "password": "good"}).status_code == 200
    app.dependency_overrides.clear()
    bad = _client_with(FakeSession(results=[FakeResult(scalar=user)]))
    assert bad.post("/auth/login", json={"email": "l@firm.com", "password": "no"}).status_code == 401
