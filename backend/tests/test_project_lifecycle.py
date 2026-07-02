"""Project lifecycle: archive (reversible, member) / delete (permanent, admin).

Org isolation, RBAC, audit-trail writes, and the archived_at flag surface.
Default-list/dashboard *filtering* runs real SQL (archived_at IS NULL) and is
covered by live verification against Postgres, not FakeSession.
"""
import uuid

from fastapi.testclient import TestClient

from app.auth.deps import get_current_user, get_db
from app.main import app
from app.models import AuditLog, Membership, MembershipRole, Project, ProjectStatus, User
from tests.fakes import FakeResult, FakeSession


def _user():
    return User(id=uuid.uuid4(), email="ca@firm.com", password_hash="x", is_active=True)


def _client(session, user):
    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def _setup(role=MembershipRole.member, member_of_project_org=True, archived_at=None,
           extra_results=0):
    user = _user()
    cid = uuid.uuid4()
    project = Project(id=uuid.uuid4(), company_id=cid, name="Tower A",
                      status=ProjectStatus.completed, archived_at=archived_at)
    m_cid = cid if member_of_project_org else uuid.uuid4()
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=m_cid, role=role)
    results = [FakeResult(scalar=membership, scalars=[membership])] * (2 + extra_results)
    session = FakeSession(results=results, get_obj=project)
    return _client(session, user), session, project


# -- archive / unarchive ------------------------------------------------------
def test_member_can_archive_project():
    client, session, project = _setup()
    resp = client.post(f"/projects/{project.id}/archive")
    assert resp.status_code == 200
    assert resp.json()["archived_at"] is not None
    assert project.archived_at is not None
    audits = session.added_of(AuditLog)
    assert len(audits) == 1 and audits[0].action == "project.archived"
    assert audits[0].company_id == project.company_id


def test_unarchive_restores_project():
    from datetime import datetime, timezone
    client, session, project = _setup(archived_at=datetime.now(timezone.utc))
    resp = client.post(f"/projects/{project.id}/unarchive")
    assert resp.status_code == 200
    assert resp.json()["archived_at"] is None
    assert project.archived_at is None
    assert session.added_of(AuditLog)[0].action == "project.unarchived"


def test_archive_is_idempotent_no_duplicate_audit():
    from datetime import datetime, timezone
    client, session, project = _setup(archived_at=datetime.now(timezone.utc))
    resp = client.post(f"/projects/{project.id}/archive")
    assert resp.status_code == 200
    assert session.added_of(AuditLog) == []   # already archived: no new event


def test_archive_org_isolation_404_for_outsider():
    client, session, project = _setup(member_of_project_org=False)
    resp = client.post(f"/projects/{project.id}/archive")
    assert resp.status_code == 404            # not visible across orgs
    assert project.archived_at is None


# -- permanent delete ---------------------------------------------------------
def test_delete_requires_admin_403_for_member():
    client, session, project = _setup(role=MembershipRole.member)
    resp = client.delete(f"/projects/{project.id}")
    assert resp.status_code == 403
    assert session.added_of(AuditLog) == []   # nothing recorded, nothing deleted


def test_admin_delete_succeeds_and_audits():
    client, session, project = _setup(role=MembershipRole.admin, extra_results=1)
    resp = client.delete(f"/projects/{project.id}")
    assert resp.status_code == 204
    audits = session.added_of(AuditLog)
    assert len(audits) == 1 and audits[0].action == "project.deleted"
    assert audits[0].before["name"] == "Tower A"
    assert session.commits == 1


def test_delete_org_isolation_404_for_outsider():
    client, session, project = _setup(role=MembershipRole.admin, member_of_project_org=False)
    resp = client.delete(f"/projects/{project.id}")
    assert resp.status_code == 404


# -- surface --------------------------------------------------------------------
def test_project_out_includes_archived_at():
    client, _, project = _setup()
    resp = client.get(f"/projects/{project.id}")
    assert resp.status_code == 200
    assert "archived_at" in resp.json() and resp.json()["archived_at"] is None
