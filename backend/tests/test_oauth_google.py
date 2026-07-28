"""Google login via Supabase: JWKS verification, account resolution, and the
additive POST /auth/google endpoint. The existing email/password + JWT +
refresh-token system (test_auth.py) is untouched by any of this."""
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.auth import supabase_jwt
from app.auth.deps import get_db
from app.auth.supabase_jwt import SupabaseNotConfigured, verify_supabase_token
from app.auth.tokens import TokenError
from app.main import app
from app.models import Membership, MembershipRole, Organization, User
from app.services import oauth_google
from tests.fakes import FakeResult, FakeSession


# -- JWKS verification -------------------------------------------------------
@pytest.fixture
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJwksClient:
    def __init__(self, public_key):
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(self._public_key)


_TEST_ISSUER = "https://project.supabase.co/auth/v1"


def _sign(private_key, *, sub="user-sub-123", email="person@example.com",
         aud="authenticated", email_verified=True, iss=_TEST_ISSUER, **overrides):
    payload = {"sub": sub, "email": email, "aud": aud, "email_verified": email_verified, **overrides}
    if iss is not None:  # iss=None lets a test mint a token with NO issuer claim
        payload["iss"] = iss
    return jwt.encode(payload, private_key, algorithm="RS256")


def test_verify_supabase_token_roundtrip(monkeypatch, rsa_keypair):
    private_key, public_key = rsa_keypair
    monkeypatch.setenv("VA_SUPABASE_URL", "https://project.supabase.co")
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr(supabase_jwt, "_jwks_client", lambda url: _FakeJwksClient(public_key))

    token = _sign(private_key)
    claims = verify_supabase_token(token)
    assert claims.sub == "user-sub-123"
    assert claims.email == "person@example.com"
    assert claims.email_verified is True
    get_settings.cache_clear()


def test_verify_supabase_token_rejects_wrong_audience(monkeypatch, rsa_keypair):
    private_key, public_key = rsa_keypair
    monkeypatch.setenv("VA_SUPABASE_URL", "https://project.supabase.co")
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr(supabase_jwt, "_jwks_client", lambda url: _FakeJwksClient(public_key))

    token = _sign(private_key, aud="some-other-audience")
    with pytest.raises(TokenError):
        verify_supabase_token(token)
    get_settings.cache_clear()


def test_verify_supabase_token_rejects_tampered_signature(monkeypatch, rsa_keypair):
    private_key, public_key = rsa_keypair
    monkeypatch.setenv("VA_SUPABASE_URL", "https://project.supabase.co")
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr(supabase_jwt, "_jwks_client", lambda url: _FakeJwksClient(public_key))

    token = _sign(private_key) + "x"
    with pytest.raises(TokenError):
        verify_supabase_token(token)
    get_settings.cache_clear()


def test_verify_supabase_token_rejects_wrong_issuer(monkeypatch, rsa_keypair):
    """A validly-signed token minted by a DIFFERENT Supabase project (or any
    other issuer) must be rejected even if signature/audience pass."""
    private_key, public_key = rsa_keypair
    monkeypatch.setenv("VA_SUPABASE_URL", "https://project.supabase.co")
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr(supabase_jwt, "_jwks_client", lambda url: _FakeJwksClient(public_key))

    token = _sign(private_key, iss="https://attacker-project.supabase.co/auth/v1")
    with pytest.raises(TokenError):
        verify_supabase_token(token)
    get_settings.cache_clear()


def test_verify_supabase_token_rejects_missing_issuer(monkeypatch, rsa_keypair):
    private_key, public_key = rsa_keypair
    monkeypatch.setenv("VA_SUPABASE_URL", "https://project.supabase.co")
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr(supabase_jwt, "_jwks_client", lambda url: _FakeJwksClient(public_key))

    token = _sign(private_key, iss=None)   # no iss claim at all
    with pytest.raises(TokenError):
        verify_supabase_token(token)
    get_settings.cache_clear()


def test_verify_supabase_token_missing_email_verified_defaults_false(monkeypatch, rsa_keypair):
    """Fail closed: a token with NO email_verified claim must come back
    unverified, so the service layer refuses to link it into an existing
    account by email."""
    private_key, public_key = rsa_keypair
    monkeypatch.setenv("VA_SUPABASE_URL", "https://project.supabase.co")
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr(supabase_jwt, "_jwks_client", lambda url: _FakeJwksClient(public_key))

    token = jwt.encode({"sub": "s", "email": "a@b.co", "aud": "authenticated",
                        "iss": _TEST_ISSUER}, private_key, algorithm="RS256")
    assert verify_supabase_token(token).email_verified is False
    get_settings.cache_clear()


def test_verify_supabase_token_email_verified_in_user_metadata(monkeypatch, rsa_keypair):
    """A token with email_verified nested inside user_metadata (and absent at
    the top level) must be successfully verified as True."""
    private_key, public_key = rsa_keypair
    monkeypatch.setenv("VA_SUPABASE_URL", "https://project.supabase.co")
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr(supabase_jwt, "_jwks_client", lambda url: _FakeJwksClient(public_key))

    payload = {
        "sub": "user-sub-123",
        "email": "person@example.com",
        "aud": "authenticated",
        "iss": _TEST_ISSUER,
        "user_metadata": {"email_verified": True}
    }
    token = jwt.encode(payload, private_key, algorithm="RS256")
    claims = verify_supabase_token(token)
    assert claims.sub == "user-sub-123"
    assert claims.email == "person@example.com"
    assert claims.email_verified is True
    get_settings.cache_clear()


def test_verify_supabase_token_not_configured_without_url(monkeypatch):
    # Explicitly override to empty (not just delenv) — a real deployment's
    # backend/.env may itself set VA_SUPABASE_URL, and pydantic-settings
    # falls back to reading that file once the env var is merely deleted.
    monkeypatch.setenv("VA_SUPABASE_URL", "")
    from app.config import get_settings
    get_settings.cache_clear()
    with pytest.raises(SupabaseNotConfigured):
        verify_supabase_token("irrelevant")
    get_settings.cache_clear()


# -- account resolution -------------------------------------------------------
def _claims(**overrides):
    defaults = dict(sub="sub-1", email="person@example.com", email_verified=True)
    defaults.update(overrides)
    return supabase_jwt.SupabaseClaims(**defaults)


def test_login_or_signup_matches_existing_user_by_email():
    existing = User(id=uuid.uuid4(), email="person@example.com", password_hash="x", is_active=True)
    session = FakeSession(results=[FakeResult(scalar=existing)])
    user, is_new = oauth_google.login_or_signup_with_google(session, _claims())
    assert user is existing and is_new is False
    assert session.commits == 0  # no new rows — pure lookup


def test_login_or_signup_creates_org_user_membership_for_new_email():
    session = FakeSession(results=[FakeResult(scalar=None)])  # no existing user
    user, is_new = oauth_google.login_or_signup_with_google(session, _claims(email="new@firm.com"))
    assert is_new is True
    assert user.password_hash is None  # Google owns credentials, not this app
    orgs = session.added_of(Organization)
    memberships = session.added_of(Membership)
    assert len(orgs) == 1 and len(memberships) == 1
    assert memberships[0].role == MembershipRole.admin
    assert memberships[0].user_id == user.id and memberships[0].company_id == orgs[0].id
    assert session.commits == 1


def test_login_or_signup_rejects_unverified_email():
    session = FakeSession(results=[FakeResult(scalar=None)])
    with pytest.raises(oauth_google.UnverifiedEmail):
        oauth_google.login_or_signup_with_google(session, _claims(email_verified=False))


# -- endpoint ------------------------------------------------------------------
def _client(session):
    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_google_login_endpoint_mints_existing_token_shape(monkeypatch):
    """The endpoint's response must be indistinguishable from signup/login's
    TokenResponse — Google is just another way to obtain the same session."""
    from app.auth import router as auth_router

    existing = User(id=uuid.uuid4(), email="person@example.com", password_hash="x", is_active=True)
    monkeypatch.setattr(auth_router, "verify_supabase_token",
                       lambda token: supabase_jwt.SupabaseClaims(sub="s", email="person@example.com", email_verified=True))
    session = FakeSession(results=[FakeResult(scalar=existing)])
    resp = _client(session).post("/auth/google", json={"supabase_access_token": "fake"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "person@example.com"
    assert "access_token" in body and "refresh_token" in body


def test_google_login_endpoint_401_on_invalid_token(monkeypatch):
    from app.auth import router as auth_router

    def _raise(token):
        raise TokenError("bad token")
    monkeypatch.setattr(auth_router, "verify_supabase_token", _raise)
    resp = _client(FakeSession()).post("/auth/google", json={"supabase_access_token": "bad"})
    assert resp.status_code == 401


def test_google_login_endpoint_503_when_not_configured(monkeypatch):
    from app.auth import router as auth_router

    def _raise(token):
        raise SupabaseNotConfigured("no url")
    monkeypatch.setattr(auth_router, "verify_supabase_token", _raise)
    resp = _client(FakeSession()).post("/auth/google", json={"supabase_access_token": "x"})
    assert resp.status_code == 503


def test_google_login_endpoint_401_on_unverified_email(monkeypatch):
    from app.auth import router as auth_router

    monkeypatch.setattr(auth_router, "verify_supabase_token",
                       lambda token: supabase_jwt.SupabaseClaims(sub="s", email="x@y.com", email_verified=False))
    resp = _client(FakeSession(results=[FakeResult(scalar=None)])).post(
        "/auth/google", json={"supabase_access_token": "x"},
    )
    assert resp.status_code == 401


def test_google_login_endpoint_401_for_disabled_account(monkeypatch):
    """An admin-disabled account must not be resurrectable via Google login —
    the same is_active gate password login already enforces."""
    from app.auth import router as auth_router

    disabled = User(id=uuid.uuid4(), email="person@example.com", password_hash="x", is_active=False)
    monkeypatch.setattr(auth_router, "verify_supabase_token",
                       lambda token: supabase_jwt.SupabaseClaims(sub="s", email="person@example.com", email_verified=True))
    session = FakeSession(results=[FakeResult(scalar=disabled)])
    resp = _client(session).post("/auth/google", json={"supabase_access_token": "fake"})
    assert resp.status_code == 401


def test_existing_login_signup_refresh_endpoints_unaffected():
    """Sanity check that adding /auth/google didn't disturb the existing
    routes' registration/behavior."""
    resp = _client(FakeSession(results=[FakeResult(scalar=None)])).post(
        "/auth/signup",
        json={"email": "still@works.com", "password": "pw123456", "org_name": "Org"},
    )
    # Signup is non-enumerating (202 + generic body) — tokens come from the
    # follow-up /auth/login the frontend performs.
    assert resp.status_code == 202
    assert "message" in resp.json()
