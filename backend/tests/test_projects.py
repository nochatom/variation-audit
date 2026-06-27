"""Projects (.3): parsing, project service, and endpoints (no Postgres)."""
import uuid

from fastapi.testclient import TestClient

from app import parsing
from app.auth.deps import get_current_user, get_db
from app.main import app
from app.models import (
    Document,
    Membership,
    MembershipRole,
    Project,
    ProjectStatus,
    SourceType,
    User,
)
from app.services import projects as project_service
from tests.fakes import FakeResult, FakeSession


# -- parsing ---------------------------------------------------------------
def test_extract_text_plain():
    assert parsing.extract_text("note.txt", b"\xef\xbb\xbfhello") == "hello"  # strips BOM


def test_kind_to_source_type():
    assert parsing.kind_to_source_type("minutes") == SourceType.meeting_note
    assert parsing.kind_to_source_type("whatever") == SourceType.document


def test_parse_comms_csv_aliased_headers():
    csv_bytes = b"From,Date,Message\nJ Smith,2026-03-05,Please add 3 GPOs\n,,\n"
    rows = parsing.parse_comms_csv(csv_bytes)
    assert len(rows) == 1                     # blank-text row skipped
    assert rows[0]["author"] == "J Smith"
    assert rows[0]["text"] == "Please add 3 GPOs"


# -- project service -------------------------------------------------------
def test_create_project_scopes_to_company():
    cid, uid = uuid.uuid4(), uuid.uuid4()
    session = FakeSession()
    p = project_service.create_project(session, company_id=cid, created_by=uid,
                                       name="Tower A", contract_text="...", state="NSW")
    assert p.company_id == cid and p.name == "Tower A" and p.state == "NSW"
    assert session.commits == 1


def test_get_project_org_scoped():
    cid, pid = uuid.uuid4(), uuid.uuid4()
    project = Project(id=pid, company_id=cid, name="X")
    found = FakeSession(results=[FakeResult(scalar=project)])
    assert project_service.get_project(found, cid, pid) is project
    missing = FakeSession(results=[FakeResult(scalar=None)])
    assert project_service.get_project(missing, uuid.uuid4(), pid) is None


def test_add_document_writes_to_store_and_registers_row():
    puts = {}

    class FakeStore:
        def put(self, key, data):
            puts[key] = data
            return key

    session = FakeSession()
    doc = project_service.add_document(
        session, FakeStore(), company_id=uuid.uuid4(), project_id=uuid.uuid4(),
        source_type=SourceType.email, content="hello", source="J", occurred_at="2026-03-05",
    )
    assert isinstance(doc, Document)
    assert doc.storage_key in puts and puts[doc.storage_key] == "hello"
    assert doc.source_type == SourceType.email
    assert session.added_of(Document) == [doc]


# -- endpoints -------------------------------------------------------------
def _fake_user():
    return User(id=uuid.uuid4(), email="ca@firm.com", password_hash="x", is_active=True)


def _with(session, user):
    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_create_project_endpoint_requires_membership_then_creates():
    user = _fake_user()
    cid = uuid.uuid4()
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid,
                            role=MembershipRole.admin)
    client = _with(FakeSession(results=[FakeResult(scalar=membership)]), user)
    resp = client.post("/projects", json={"company_id": str(cid), "name": "Tower A"})
    assert resp.status_code == 201
    assert resp.json()["company_id"] == str(cid)


def test_create_project_endpoint_403_when_not_member():
    user = _fake_user()
    client = _with(FakeSession(results=[FakeResult(scalar=None)]), user)  # no membership
    resp = client.post("/projects", json={"company_id": str(uuid.uuid4()), "name": "X"})
    assert resp.status_code == 403


def test_list_projects_endpoint():
    user = _fake_user()
    cid = uuid.uuid4()
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid)
    project = Project(id=uuid.uuid4(), company_id=cid, name="Tower A",
                      status=ProjectStatus.in_progress)
    client = _with(
        FakeSession(results=[FakeResult(scalar=membership), FakeResult(scalars=[project])]),
        user,
    )
    resp = client.get(f"/projects?company_id={cid}")
    assert resp.status_code == 200
    assert [p["name"] for p in resp.json()] == ["Tower A"]
