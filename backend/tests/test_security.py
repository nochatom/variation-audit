"""Security & permissions (.19): RBAC guard + member management."""
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user, get_db, require_admin
from app.main import app
from app.models import AuditLog, Membership, MembershipRole, User
from app.services import orgs as org_service
from tests.fakes import FakeResult, FakeSession


def _user():
    return User(id=uuid.uuid4(), email="a@firm.com", password_hash="x", is_active=True)


def _membership(user_id, company_id, role=MembershipRole.member):
    return Membership(id=uuid.uuid4(), user_id=user_id, company_id=company_id, role=role)


# -- require_admin guard ---------------------------------------------------
def test_require_admin_allows_admin():
    user, cid = _user(), uuid.uuid4()
    m = _membership(user.id, cid, MembershipRole.admin)
    assert require_admin(FakeSession(results=[FakeResult(scalar=m)]), user, cid) is m


def test_require_admin_rejects_member():
    user, cid = _user(), uuid.uuid4()
    m = _membership(user.id, cid, MembershipRole.member)
    with pytest.raises(HTTPException) as ei:
        require_admin(FakeSession(results=[FakeResult(scalar=m)]), user, cid)
    assert ei.value.status_code == 403


# -- service ---------------------------------------------------------------
def test_add_member_existing_user_audited():
    actor, cid = _user(), uuid.uuid4()
    target = User(id=uuid.uuid4(), email="new@firm.com", password_hash="x")
    # execute calls: 1) user-by-email -> target  2) existing membership -> None
    session = FakeSession(results=[FakeResult(scalar=target), FakeResult(scalar=None)])
    m = org_service.add_member(session, company_id=cid, actor=actor,
                               email="new@firm.com", role=MembershipRole.member)
    assert m.user_id == target.id and m.role == MembershipRole.member
    assert any(a.action == "member.added" for a in session.added_of(AuditLog))
    assert session.commits == 1


def test_add_member_unknown_email_raises():
    session = FakeSession(results=[FakeResult(scalar=None)])
    with pytest.raises(org_service.UserNotFound):
        org_service.add_member(session, company_id=uuid.uuid4(), actor=_user(),
                               email="ghost@firm.com")


def test_demote_last_admin_blocked():
    actor, cid = _user(), uuid.uuid4()
    target_id = uuid.uuid4()
    admin_m = _membership(target_id, cid, MembershipRole.admin)
    # _membership lookup -> admin_m ; _admins -> [admin_m] (only one)
    session = FakeSession(results=[FakeResult(scalar=admin_m),
                                   FakeResult(scalars=[admin_m])])
    with pytest.raises(org_service.LastAdmin):
        org_service.set_role(session, company_id=cid, actor=actor,
                             target_user_id=target_id, role=MembershipRole.member)


def test_remove_last_admin_blocked():
    actor, cid = _user(), uuid.uuid4()
    target_id = uuid.uuid4()
    admin_m = _membership(target_id, cid, MembershipRole.admin)
    session = FakeSession(results=[FakeResult(scalar=admin_m),
                                   FakeResult(scalars=[admin_m])])
    with pytest.raises(org_service.LastAdmin):
        org_service.remove_member(session, company_id=cid, actor=actor,
                                  target_user_id=target_id)
    assert session.deleted == []


def test_remove_member_with_other_admin_ok():
    actor, cid = _user(), uuid.uuid4()
    target_id = uuid.uuid4()
    target_m = _membership(target_id, cid, MembershipRole.admin)
    other = _membership(uuid.uuid4(), cid, MembershipRole.admin)
    session = FakeSession(results=[FakeResult(scalar=target_m),
                                   FakeResult(scalars=[target_m, other])])
    org_service.remove_member(session, company_id=cid, actor=actor, target_user_id=target_id)
    assert session.deleted == [target_m]


# -- endpoints -------------------------------------------------------------
def _client(session, user):
    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_add_member_endpoint_requires_admin():
    user, cid = _user(), uuid.uuid4()
    member_m = _membership(user.id, cid, MembershipRole.member)   # not admin
    client = _client(FakeSession(results=[FakeResult(scalar=member_m)]), user)
    resp = client.post(f"/orgs/{cid}/members", json={"email": "x@firm.com"})
    assert resp.status_code == 403


def test_add_member_endpoint_admin_ok():
    user, cid = _user(), uuid.uuid4()
    admin_m = _membership(user.id, cid, MembershipRole.admin)
    target = User(id=uuid.uuid4(), email="new@firm.com", password_hash="x")
    # require_admin: ensure_member execute -> admin_m
    # enforce_seat_limit: subscription lookup -> None (lazily created Free);
    #                     seat count -> 1 existing member (under Free's 3)
    # add_member: user-by-email -> target ; existing membership -> None
    session = FakeSession(results=[FakeResult(scalar=admin_m),
                                   FakeResult(scalar=None),
                                   FakeResult(scalars=[admin_m.id]),
                                   FakeResult(scalar=target),
                                   FakeResult(scalar=None)])
    resp = _client(session, user).post(f"/orgs/{cid}/members",
                                       json={"email": "new@firm.com", "role": "member"})
    assert resp.status_code == 201
    assert resp.json()["role"] == "member"


def test_add_member_endpoint_blocked_at_seat_limit():
    """Direct member-add must enforce the plan seat cap exactly like the
    invitation flow does — it was previously a way around it."""
    user, cid = _user(), uuid.uuid4()
    admin_m = _membership(user.id, cid, MembershipRole.admin)
    seat_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]   # Free plan cap = 3, already full
    session = FakeSession(results=[FakeResult(scalar=admin_m),
                                   FakeResult(scalar=None),
                                   FakeResult(scalars=seat_ids)])
    resp = _client(session, user).post(f"/orgs/{cid}/members",
                                       json={"email": "new@firm.com", "role": "member"})
    assert resp.status_code == 402
    assert resp.json()["detail"]["error_code"] == "seat_limit_exceeded"
