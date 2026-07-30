"""Integration test against a real local Postgres.

refresh_tokens.rotate() sets replaced_by_id, a real self-referential foreign
key (refresh_tokens.id -> refresh_tokens.id). FakeSession has no concept of
SQL execution order or foreign-key constraints, so a bug where the new row's
INSERT and the old row's UPDATE are flushed in the wrong order — which
Postgres rejects with a ForeignKeyViolation — passes every FakeSession-based
test in test_refresh_tokens.py while failing on every real refresh in
production. This is the only test that can catch that class of bug.

Skipped automatically if no reachable Postgres is configured (VA_DATABASE_URL)
— CI environments without a database still pass the rest of the suite.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.auth import refresh_tokens as rt
from app.models import RefreshToken, User

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
def user_id():
    with session_factory() as session:
        user = User(id=uuid.uuid4(), email=f"rt-live-test-{uuid.uuid4()}@example.com",
                   password_hash="x", is_active=True)
        session.add(user)
        session.commit()
        uid = user.id

    yield uid

    with session_factory() as session:
        session.execute(text("DELETE FROM refresh_tokens WHERE user_id = :u"), {"u": str(uid)})
        session.execute(text("DELETE FROM users WHERE id = :u"), {"u": str(uid)})
        session.commit()


def test_rotate_persists_correctly_against_real_postgres(user_id):
    """The exact scenario that broke: rotate()'s INSERT (new row) and UPDATE
    (old row's replaced_by_id, revoked_at) must both land in the database,
    with the FK satisfied, without raising IntegrityError."""
    with session_factory() as session:
        raw1 = rt.issue(session, user_id)

    with session_factory() as session:
        raw2, uid = rt.rotate(session, raw1)  # must not raise ForeignKeyViolation
        assert uid == user_id

    # Fresh session/connection — proves the writes were actually committed,
    # not just correct in the process's in-memory identity map.
    with session_factory() as fresh:
        old_id, _ = rt._decode(raw1)
        new_id, _ = rt._decode(raw2)
        old = fresh.get(RefreshToken, old_id)
        new = fresh.get(RefreshToken, new_id)
        assert old.revoked_at is not None
        assert old.replaced_by_id == new_id
        assert new.revoked_at is None


def test_rotate_reuse_detection_persists_against_real_postgres(user_id):
    """Presenting an already-rotated token must revoke the whole chain in the
    database, not just in memory — verified via a fresh session/connection."""
    with session_factory() as session:
        raw1 = rt.issue(session, user_id)
    with session_factory() as session:
        raw2, _ = rt.rotate(session, raw1)
    with session_factory() as session:
        try:
            rt.rotate(session, raw1)
            assert False, "expected TokenReused"
        except rt.TokenReused:
            pass

    with session_factory() as fresh:
        new_id, _ = rt._decode(raw2)
        new_row = fresh.get(RefreshToken, new_id)
        assert new_row.revoked_at is not None, "reuse detection must revoke the rotated-to row too"
