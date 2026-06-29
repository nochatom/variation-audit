"""Notifications (.18): list, unread count, mark read/all, endpoints."""
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.auth.deps import get_current_user, get_db
from app.main import app
from app.models import Notification, User
from app.services import notifications as notif_service
from tests.fakes import FakeResult, FakeSession


def _user():
    return User(id=uuid.uuid4(), email="ca@firm.com", password_hash="x", is_active=True)


def _notif(user_id, read=False):
    n = Notification(id=uuid.uuid4(), company_id=uuid.uuid4(), user_id=user_id,
                     type="analysis_complete", payload={"job_id": "j1"})
    n.read_at = datetime.now(timezone.utc) if read else None
    return n


# -- service ---------------------------------------------------------------
def test_unread_count():
    user = _user()
    session = FakeSession(results=[FakeResult(scalars=[_notif(user.id), _notif(user.id)])])
    assert notif_service.unread_count(session, user) == 2


def test_mark_read_sets_timestamp_and_commits():
    user = _user()
    n = _notif(user.id)
    session = FakeSession(results=[FakeResult(scalar=n)])
    out = notif_service.mark_read(session, user, n.id)
    assert out is n and n.read_at is not None
    assert session.commits == 1


def test_mark_read_missing_returns_none():
    session = FakeSession(results=[FakeResult(scalar=None)])
    assert notif_service.mark_read(session, _user(), uuid.uuid4()) is None


def test_mark_all_read():
    user = _user()
    unread = [_notif(user.id), _notif(user.id), _notif(user.id)]
    session = FakeSession(results=[FakeResult(scalars=unread)])
    assert notif_service.mark_all_read(session, user) == 3
    assert all(n.read_at is not None for n in unread)
    assert session.commits == 1


# -- endpoints -------------------------------------------------------------
def _client(session, user):
    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_list_endpoint():
    user = _user()
    n = _notif(user.id)
    session = FakeSession(results=[FakeResult(scalars=[n])])
    resp = _client(session, user).get("/notifications")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["type"] == "analysis_complete" and body[0]["read"] is False


def test_unread_count_endpoint():
    user = _user()
    session = FakeSession(results=[FakeResult(scalars=[_notif(user.id)])])
    resp = _client(session, user).get("/notifications/unread-count")
    assert resp.status_code == 200 and resp.json()["count"] == 1


def test_mark_read_endpoint():
    user = _user()
    n = _notif(user.id)
    session = FakeSession(results=[FakeResult(scalar=n)])
    resp = _client(session, user).post(f"/notifications/{n.id}/read")
    assert resp.status_code == 200 and resp.json()["read"] is True
