"""Google login via Supabase (.25): JWKS verification, account resolution,
and the additive POST /auth/google endpoint. The existing email/password +
JWT + refresh-token system (test_auth.py) is untouched by any of this."""
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from datetime import datetime, timedelta, timezone

from app.auth import supabase_jwt
from app.auth.deps import get_db
from app.auth.supabase_jwt import SupabaseNotConfigured, verify_supabase_token
from app.auth.tokens import TokenError
from app.main import app
from app.models import Invitation, Membership, MembershipRole, Organization, User
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


def _sign(private_key, *, sub="user-sub-123", email="person@example.com",
         aud="authenticated", email_verified=True, **overrides):
    payload = {"sub": sub, "email": email, "aud": aud, "email_verified": email_verified, **overrides}
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


def test_verify_supabase_token_rejects_unverified_email(monkeypatch, rsa_keypair):
    private_key, public_key = rsa_keypair
    monkeypatch.setenv("VA_SUPABASE_URL", "https://project.supabase.co")
    from app.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr(supabase_jwt, "_jwks_client", lambda url: _FakeJwksClient(public_key))

    token = _sign(private_key, email_verified=False)
    claims = verify_supabase_token(token)
    assert claims.email_verified is False  # verification succeeds; the SERVICE layer rejects it
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


def test_verify_supabase_token_not_configured_without_url(monkeypatch):
    monkeypatch.delenv("VA_SUPABASE_URL", raising=False)
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


def _pending_invitation(email, company_id=None):
    return Invitation(
        id=uuid.uuid4(), company_id=company_id or uuid.uuid4(), email=email,
        role=MembershipRole.member, token_hash="irrelevant", invited_by=uuid.uuid4(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )


def test_login_or_signup_joins_invited_org_instead_of_creating_new_org():
    """A first-time Google sign-in for an email with a pending invitation
    must join the inviting org, not get a stray brand-new Organization —
    the fix for the gap flagged in the regression risk report."""
    inv = _pending_invitation("invited@firm.com")
    session = FakeSession(results=[
        FakeResult(scalar=None),          # _user_by_email: no existing account
        FakeResult(scalars=[inv]),        # pending invitations for this email
        FakeResult(scalar=None),          # _membership: not yet a member of inv.company_id
    ])
    user, is_new = oauth_google.login_or_signup_with_google(session, _claims(email="invited@firm.com"))

    assert is_new is True
    assert session.added_of(Organization) == []  # no new org created
    memberships = session.added_of(Membership)
    assert len(memberships) == 1
    assert memberships[0].company_id == inv.company_id
    assert memberships[0].role == MembershipRole.member  # the invitation's role, not admin
    assert memberships[0].user_id == user.id
    assert inv.accepted_at is not None and inv.accepted_by == user.id
    assert session.commits == 1


def test_login_or_signup_joins_every_pending_org_for_the_same_email():
    """Multiple pending invitations to the same email (different orgs) are
    all accepted, not just the first."""
    inv_a = _pending_invitation("multi@firm.com")
    inv_b = _pending_invitation("multi@firm.com")
    session = FakeSession(results=[
        FakeResult(scalar=None),
        FakeResult(scalars=[inv_a, inv_b]),
        FakeResult(scalar=None),   # _membership check for inv_a
        FakeResult(scalar=None),   # _membership check for inv_b
    ])
    user, is_new = oauth_google.login_or_signup_with_google(session, _claims(email="multi@firm.com"))
    memberships = session.added_of(Membership)
    assert len(memberships) == 2
    assert {m.company_id for m in memberships} == {inv_a.company_id, inv_b.company_id}
    assert session.added_of(Organization) == []


def test_login_or_signup_ignores_expired_or_accepted_invitations():
    """Only a genuinely pending invitation should divert Google sign-in away
    from creating a new org — an expired/already-accepted/revoked one (which
    the real DB query filters out via WHERE, simulated here by simply not
    returning it) must not block normal new-org provisioning."""
    session = FakeSession(results=[
        FakeResult(scalar=None),   # _user_by_email
        FakeResult(scalars=[]),    # no genuinely-pending invitations match
    ])
    user, is_new = oauth_google.login_or_signup_with_google(session, _claims(email="new@firm.com"))
    assert is_new is True
    assert len(session.added_of(Organization)) == 1  # falls back to normal first-time signup


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


def test_existing_login_signup_refresh_endpoints_unaffected():
    """Sanity check that adding /auth/google didn't disturb the existing
    routes' registration/behavior."""
    resp = _client(FakeSession(results=[FakeResult(scalar=None)])).post(
        "/auth/signup",
        json={"email": "still@works.com", "password": "pw123456", "org_name": "Org"},
    )
    assert resp.status_code == 201
    assert "access_token" in resp.json()
