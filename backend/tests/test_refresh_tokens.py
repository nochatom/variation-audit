"""Refresh token rotation + revocation (.2.1): service logic and endpoints."""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.auth import refresh_tokens as rt
from app.auth.deps import get_current_user, get_db
from app.main import app
from app.models import RefreshToken, User
from tests.fakes import FakeResult, FakeSession


def _now():
    return datetime.now(timezone.utc)


def _fixture_row(*, user_id=None, revoked=False, expired=False):
    """Build a RefreshToken row + its matching raw token, encoded the same way
    the module itself does (so rotate()/revoke() can validate it)."""
    user_id = user_id or uuid.uuid4()
    secret = "test-secret-abc123"
    row = RefreshToken(
        id=uuid.uuid4(), user_id=user_id, token_hash=rt._hash(secret),
        expires_at=_now() + (timedelta(days=-1) if expired else timedelta(days=30)),
        revoked_at=_now() if revoked else None,
    )
    raw = rt._encode(row.id, secret)
    return row, raw


# -- issue --------------------------------------------------------------------
def test_issue_creates_row_and_returns_encoded_token():
    session = FakeSession()
    uid = uuid.uuid4()
    raw = rt.issue(session, uid)
    assert "." in raw
    assert session.commits == 1
    rows = session.added_of(RefreshToken)
    assert len(rows) == 1 and rows[0].user_id == uid
    assert rows[0].token_hash == rt._hash(raw.split(".", 1)[1])


# -- rotate ---------------------------------------------------------------------
def test_rotate_valid_token_revokes_old_and_returns_new():
    row, raw = _fixture_row()
    session = FakeSession(get_obj=row)
    new_raw, user_id = rt.rotate(session, raw)
    assert new_raw != raw
    assert user_id == row.user_id
    assert row.revoked_at is not None
    assert row.replaced_by_id is not None
    # 1 commit from issue() inside rotate(), 1 more from rotate() itself
    assert session.commits == 2


def test_rotate_malformed_token_raises():
    session = FakeSession()
    try:
        rt.rotate(session, "not-a-valid-token")
        assert False, "expected RefreshTokenError"
    except rt.RefreshTokenError:
        pass


def test_rotate_unknown_token_raises():
    session = FakeSession(get_obj=None)
    _, raw = _fixture_row()
    try:
        rt.rotate(session, raw)
        assert False, "expected RefreshTokenError"
    except rt.RefreshTokenError:
        pass


def test_rotate_wrong_secret_raises():
    row, _ = _fixture_row()
    session = FakeSession(get_obj=row)
    forged = rt._encode(row.id, "wrong-secret")
    try:
        rt.rotate(session, forged)
        assert False, "expected RefreshTokenError"
    except rt.RefreshTokenError:
        pass


def test_rotate_expired_token_raises():
    row, raw = _fixture_row(expired=True)
    session = FakeSession(get_obj=row)
    try:
        rt.rotate(session, raw)
        assert False, "expected RefreshTokenError"
    except rt.RefreshTokenError:
        pass


def test_rotate_reused_token_revokes_all_sessions():
    """Presenting an already-revoked (rotated) token signals theft: every
    active refresh token for that user must be revoked as a precaution."""
    uid = uuid.uuid4()
    row, raw = _fixture_row(user_id=uid, revoked=True)
    other_active = RefreshToken(id=uuid.uuid4(), user_id=uid, token_hash="x",
                                expires_at=_now() + timedelta(days=1))
    # get(RefreshToken, id) -> the reused row ; revoke_all's select -> [other_active]
    session = FakeSession(results=[FakeResult(scalars=[other_active])], get_obj=row)
    try:
        rt.rotate(session, raw)
        assert False, "expected TokenReused"
    except rt.TokenReused:
        pass
    assert other_active.revoked_at is not None


# -- revoke / revoke_all --------------------------------------------------------
def test_revoke_marks_row_revoked():
    row, raw = _fixture_row()
    session = FakeSession(get_obj=row)
    assert rt.revoke(session, raw) is True
    assert row.revoked_at is not None


def test_revoke_already_revoked_returns_false():
    row, raw = _fixture_row(revoked=True)
    session = FakeSession(get_obj=row)
    assert rt.revoke(session, raw) is False


def test_revoke_all_marks_every_active_row():
    uid = uuid.uuid4()
    a = RefreshToken(id=uuid.uuid4(), user_id=uid, token_hash="a", expires_at=_now() + timedelta(days=1))
    b = RefreshToken(id=uuid.uuid4(), user_id=uid, token_hash="b", expires_at=_now() + timedelta(days=1))
    session = FakeSession(results=[FakeResult(scalars=[a, b])])
    count = rt.revoke_all(session, uid)
    assert count == 2
    assert a.revoked_at is not None and b.revoked_at is not None


# -- endpoints --------------------------------------------------------------------
def _client(session, user=None):
    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_login_endpoint_returns_refresh_token():
    from app.auth.security import hash_password
    user = User(id=uuid.uuid4(), email="l@firm.com", password_hash=hash_password("goodpass1"), is_active=True)
    session = FakeSession(results=[FakeResult(scalar=user)])
    resp = _client(session).post("/auth/login", json={"email": "l@firm.com", "password": "goodpass1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["refresh_token"] and "." in body["refresh_token"]
    assert body["access_token"]


def test_refresh_endpoint_rotates_and_returns_new_tokens():
    row, raw = _fixture_row()
    session = FakeSession(get_obj=row)
    resp = _client(session).post("/auth/refresh", json={"refresh_token": raw})
    assert resp.status_code == 200
    body = resp.json()
    assert body["refresh_token"] != raw
    assert body["access_token"]


def test_refresh_endpoint_rejects_invalid_token():
    session = FakeSession(get_obj=None)
    resp = _client(session).post("/auth/refresh", json={"refresh_token": "bogus.token"})
    assert resp.status_code == 401


def test_logout_endpoint_revokes_and_returns_204():
    row, raw = _fixture_row()
    session = FakeSession(get_obj=row)
    resp = _client(session).post("/auth/logout", json={"refresh_token": raw})
    assert resp.status_code == 204
    assert row.revoked_at is not None


def test_logout_all_endpoint_requires_auth_and_revokes():
    user = User(id=uuid.uuid4(), email="a@firm.com", password_hash="x", is_active=True)
    a = RefreshToken(id=uuid.uuid4(), user_id=user.id, token_hash="a", expires_at=_now() + timedelta(days=1))
    session = FakeSession(results=[FakeResult(scalars=[a])])
    resp = _client(session, user).post("/auth/logout-all")
    assert resp.status_code == 204
    assert a.revoked_at is not None
