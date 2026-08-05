"""Password reset (.22 auth): token issue/verify + revoke-all-sessions on reset."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth.deps import get_db
from app.auth.security import verify_password
from app.main import app
from app.models import PasswordResetToken, User
from app.services import password_reset as password_reset_service
from tests.fakes import FakeResult, FakeSession


class _MultiGetSession(FakeSession):
    """Some flows call session.get() for two different row types in one call
    (PasswordResetToken, then User) — plain FakeSession only supports one
    fixed return value, so map by class here instead."""

    def __init__(self, *, get_by_class: dict, results=None):
        super().__init__(results=results)
        self._get_by_class = get_by_class

    def get(self, cls, _pk):
        return self._get_by_class.get(cls)


def _now():
    return datetime.now(timezone.utc)


# -- create_reset_token ---------------------------------------------------
def test_create_reset_token_unknown_email_returns_none():
    session = FakeSession(results=[FakeResult(scalar=None)])
    token = password_reset_service.create_reset_token(session, email="nobody@example.com", expire_minutes=60)
    assert token is None
    # Timing parity: the not-found branch performs the SAME commit round trip
    # as the exists branch (but writes nothing) so response latency doesn't
    # reveal whether the account exists.
    assert session.commits == 1
    assert session.added_of(PasswordResetToken) == []


def test_create_reset_token_commit_parity_between_branches():
    """Both branches must end with exactly one commit — equivalent observable
    DB work whether or not the account exists."""
    unknown = FakeSession(results=[FakeResult(scalar=None)])
    password_reset_service.create_reset_token(unknown, email="nobody@example.com", expire_minutes=60)

    user = User(id=uuid.uuid4(), email="user@example.com", password_hash="hash", is_active=True)
    known = FakeSession(results=[FakeResult(scalar=user)])
    password_reset_service.create_reset_token(known, email="user@example.com", expire_minutes=60)

    assert unknown.commits == known.commits == 1


def test_create_reset_token_known_email_returns_raw_token():
    user = User(id=uuid.uuid4(), email="user@example.com", password_hash="hash", is_active=True)
    session = FakeSession(results=[FakeResult(scalar=user)])
    token = password_reset_service.create_reset_token(session, email="user@example.com", expire_minutes=60)
    assert token is not None
    assert "." in token
    assert len(session.added_of(PasswordResetToken)) == 1
    assert session.commits == 1


# -- reset_password ---------------------------------------------------------
def _make_token_row(user_id, *, secret, used_at=None, expires_delta=timedelta(hours=1)):
    return PasswordResetToken(
        id=uuid.uuid4(), user_id=user_id,
        token_hash=password_reset_service._hash(secret),
        expires_at=_now() + expires_delta, used_at=used_at,
    )


def test_reset_password_malformed_token_raises():
    session = _MultiGetSession(get_by_class={})
    with pytest.raises(password_reset_service.ResetTokenError):
        password_reset_service.reset_password(session, raw_token="not-a-real-token", new_password="newpassword123")


def test_reset_password_unknown_token_raises():
    session = _MultiGetSession(get_by_class={PasswordResetToken: None})
    raw = password_reset_service._encode(uuid.uuid4(), "some-secret")
    with pytest.raises(password_reset_service.ResetTokenError):
        password_reset_service.reset_password(session, raw_token=raw, new_password="newpassword123")


def test_reset_password_already_used_raises():
    user_id = uuid.uuid4()
    row = _make_token_row(user_id, secret="s3cr3t", used_at=_now())
    session = _MultiGetSession(get_by_class={PasswordResetToken: row})
    raw = password_reset_service._encode(row.id, "s3cr3t")
    with pytest.raises(password_reset_service.ResetTokenError):
        password_reset_service.reset_password(session, raw_token=raw, new_password="newpassword123")


def test_reset_password_expired_raises():
    user_id = uuid.uuid4()
    row = _make_token_row(user_id, secret="s3cr3t", expires_delta=timedelta(hours=-1))
    session = _MultiGetSession(get_by_class={PasswordResetToken: row})
    raw = password_reset_service._encode(row.id, "s3cr3t")
    with pytest.raises(password_reset_service.ResetTokenError):
        password_reset_service.reset_password(session, raw_token=raw, new_password="newpassword123")


def test_reset_password_success_updates_password_and_revokes_sessions():
    user_id = uuid.uuid4()
    row = _make_token_row(user_id, secret="s3cr3t")
    user = User(id=user_id, email="user@example.com", password_hash="oldhash", is_active=True)
    session = _MultiGetSession(
        get_by_class={PasswordResetToken: row, User: user},
        results=[FakeResult(scalars=[])],  # revoke_all's active-token lookup: none active
    )
    raw = password_reset_service._encode(row.id, "s3cr3t")

    returned_user = password_reset_service.reset_password(session, raw_token=raw, new_password="newpassword123")

    assert returned_user is user
    assert row.used_at is not None
    assert user.password_hash != "oldhash"
    assert verify_password("newpassword123", user.password_hash)


# -- endpoints ---------------------------------------------------------------
def _client(session):
    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_forgot_password_endpoint_always_204_unknown_email():
    session = FakeSession(results=[FakeResult(scalar=None)])
    resp = _client(session).post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert resp.status_code == 204


def test_forgot_password_endpoint_always_204_known_email():
    user = User(id=uuid.uuid4(), email="user@example.com", password_hash="hash", is_active=True)
    session = FakeSession(results=[FakeResult(scalar=user)])
    resp = _client(session).post("/auth/forgot-password", json={"email": "user@example.com"})
    assert resp.status_code == 204


def test_reset_password_endpoint_invalid_token_400s():
    session = _MultiGetSession(get_by_class={})
    resp = _client(session).post(
        "/auth/reset-password", json={"token": "garbage", "new_password": "newpassword123"}
    )
    assert resp.status_code == 400


def test_reset_password_endpoint_success_204():
    user_id = uuid.uuid4()
    row = _make_token_row(user_id, secret="s3cr3t")
    user = User(id=user_id, email="user@example.com", password_hash="oldhash", is_active=True)
    session = _MultiGetSession(
        get_by_class={PasswordResetToken: row, User: user},
        results=[FakeResult(scalars=[])],
    )
    raw = password_reset_service._encode(row.id, "s3cr3t")
    resp = _client(session).post(
        "/auth/reset-password", json={"token": raw, "new_password": "newpassword123"}
    )
    assert resp.status_code == 204


class _StatementRecordingSession(_MultiGetSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.statements = []

    def execute(self, stmt):
        self.statements.append(stmt)
        return super().execute(stmt)


def test_create_reset_token_invalidates_existing_tokens():
    user = User(id=uuid.uuid4(), email="user@example.com", password_hash="hash", is_active=True)
    session = _StatementRecordingSession(
        get_by_class={User: user},
        results=[FakeResult(scalar=user), FakeResult()],  # for user lookup + update
    )

    password_reset_service.create_reset_token(session, email="user@example.com", expire_minutes=60)

    # 1st statement is SELECT user, 2nd is UPDATE to invalidate prior tokens
    assert len(session.statements) >= 2
    update_stmt = session.statements[1]

    # Verify the update is targeted at the PasswordResetToken model
    assert update_stmt.is_update
    assert update_stmt.table.name == "password_reset_tokens"


def test_reset_password_invalidates_all_other_active_tokens():
    user_id = uuid.uuid4()
    row = _make_token_row(user_id, secret="s3cr3t")
    user = User(id=user_id, email="user@example.com", password_hash="oldhash", is_active=True)

    session = _StatementRecordingSession(
        get_by_class={PasswordResetToken: row, User: user},
        results=[FakeResult(scalars=[])],  # revoke_all's active-token lookup
    )
    raw = password_reset_service._encode(row.id, "s3cr3t")
    password_reset_service.reset_password(session, raw_token=raw, new_password="newpassword123")

    # Verify that an update statement on PasswordResetToken was executed
    update_stmts = [stmt for stmt in session.statements if stmt.is_update]
    assert len(update_stmts) == 1
    assert update_stmts[0].table.name == "password_reset_tokens"
