"""Project lifecycle: archive (reversible, member) / delete (permanent, admin).

Org isolation, RBAC, audit-trail writes, and the archived_at flag surface.
Default-list/dashboard *filtering* runs real SQL (archived_at IS NULL) and is
covered by live verification against Postgres, not FakeSession.
"""
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.auth.deps import get_current_user, get_db
from app.main import app
from app.models import AuditLog, Membership, MembershipRole, Project, ProjectStatus, User
from app.storage import get_store
from tests.fakes import FakeResult, FakeSession


class FakeStore:
    """Records delete() calls instead of touching real storage."""

    def __init__(self):
        self.deleted: list[str] = []

    def delete(self, storage_key: str) -> None:
        self.deleted.append(storage_key)


def _user():
    return User(id=uuid.uuid4(), email="ca@firm.com", password_hash="x", is_active=True)


def _client(session, user, store=None):
    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    if store is not None:
        app.dependency_overrides[get_store] = lambda: store
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def _setup(role=MembershipRole.member, member_of_project_org=True, archived_at=None,
           extra_results=0, doc_storage_keys=None):
    user = _user()
    cid = uuid.uuid4()
    project = Project(id=uuid.uuid4(), company_id=cid, name="Tower A",
                      status=ProjectStatus.completed, archived_at=archived_at)
    m_cid = cid if member_of_project_org else uuid.uuid4()
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=m_cid, role=role)
    results = [FakeResult(scalar=membership, scalars=[membership])] * 2
    if extra_results:
        # The delete path's extra execute() is the Document.storage_key query.
        results += [FakeResult(scalars=doc_storage_keys or [])] * extra_results
    session = FakeSession(results=results, get_obj=project)
    store = FakeStore() if doc_storage_keys is not None else None
    return _client(session, user, store=store), session, project, store


# -- archive / unarchive ------------------------------------------------------
def test_member_can_archive_project():
    client, session, project, _ = _setup()
    resp = client.post(f"/projects/{project.id}/archive")
    assert resp.status_code == 200
    assert resp.json()["archived_at"] is not None
    assert project.archived_at is not None
    audits = session.added_of(AuditLog)
    assert len(audits) == 1 and audits[0].action == "project.archived"
    assert audits[0].company_id == project.company_id


def test_unarchive_restores_project():
    client, session, project, _ = _setup(archived_at=datetime.now(timezone.utc))
    resp = client.post(f"/projects/{project.id}/unarchive")
    assert resp.status_code == 200
    assert resp.json()["archived_at"] is None
    assert project.archived_at is None
    assert session.added_of(AuditLog)[0].action == "project.unarchived"


def test_archive_is_idempotent_no_duplicate_audit():
    client, session, project, _ = _setup(archived_at=datetime.now(timezone.utc))
    resp = client.post(f"/projects/{project.id}/archive")
    assert resp.status_code == 200
    assert session.added_of(AuditLog) == []   # already archived: no new event


def test_archive_org_isolation_404_for_outsider():
    client, session, project, _ = _setup(member_of_project_org=False)
    resp = client.post(f"/projects/{project.id}/archive")
    assert resp.status_code == 404            # not visible across orgs
    assert project.archived_at is None


# -- permanent delete ---------------------------------------------------------
def test_delete_requires_admin_403_for_member():
    # Archived, so the only thing standing between this and success is role —
    # isolates the RBAC check from the archive-first check below.
    client, session, project, _ = _setup(role=MembershipRole.member,
                                         archived_at=datetime.now(timezone.utc))
    resp = client.delete(f"/projects/{project.id}")
    assert resp.status_code == 403
    assert session.added_of(AuditLog) == []   # nothing recorded, nothing deleted


def test_delete_rejects_active_project_409_even_for_admin():
    # The safety gate: archive-first is enforced server-side, not just hidden
    # in the UI — a direct API call from an admin still can't skip it.
    client, session, project, _ = _setup(role=MembershipRole.admin)  # archived_at=None
    resp = client.delete(f"/projects/{project.id}")
    assert resp.status_code == 409
    assert "archived" in resp.json()["detail"]
    assert session.added_of(AuditLog) == []   # nothing recorded, nothing deleted


def test_admin_delete_succeeds_and_audits():
    client, session, project, store = _setup(
        role=MembershipRole.admin, archived_at=datetime.now(timezone.utc), extra_results=1,
        doc_storage_keys=["proj/doc-a.txt", "proj/doc-b.txt"],
    )
    resp = client.delete(f"/projects/{project.id}")
    assert resp.status_code == 204
    audits = session.added_of(AuditLog)
    assert len(audits) == 1 and audits[0].action == "project.deleted"
    assert audits[0].before["name"] == "Tower A"
    assert session.commits == 1
    # storage cleanup: every document's blob deleted before the row cascade
    assert store.deleted == ["proj/doc-a.txt", "proj/doc-b.txt"]


def test_delete_with_no_documents_skips_storage_calls():
    client, session, project, store = _setup(
        role=MembershipRole.admin, archived_at=datetime.now(timezone.utc),
        extra_results=1, doc_storage_keys=[],
    )
    resp = client.delete(f"/projects/{project.id}")
    assert resp.status_code == 204
    assert store.deleted == []


def test_delete_org_isolation_404_for_outsider():
    client, session, project, _ = _setup(role=MembershipRole.admin, member_of_project_org=False)
    resp = client.delete(f"/projects/{project.id}")
    assert resp.status_code == 404


# -- surface --------------------------------------------------------------------
def test_project_out_includes_archived_at():
    client, _, project, _s = _setup()
    resp = client.get(f"/projects/{project.id}")
    assert resp.status_code == 200
    assert "archived_at" in resp.json() and resp.json()["archived_at"] is None
