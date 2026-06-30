"""RFI ingestion (.5): register CSV parser + upload endpoint."""
import uuid

from fastapi.testclient import TestClient

from app.auth.deps import get_current_user, get_db
from app.main import app
from app.models import Membership, Project, ProjectStatus, User
from app.parsing import parse_rfi_csv
from app.storage import get_store
from tests.fakes import FakeResult, FakeSession


# -- parser ----------------------------------------------------------------
def test_parse_rfi_csv_basic():
    csv = (
        "rfi_number,subject,question,response,date_raised,status\n"
        "RFI-012,Extra GPOs,Can we add 3 GPOs?,Yes proceed,05/03/2026,closed\n"
        ",,,,,\n"  # blank row -> skipped
        "RFI-013,Slab depth,Confirm slab depth?,,06/03/2026,open\n"
    )
    rows = parse_rfi_csv(csv.encode())
    assert len(rows) == 2
    assert rows[0]["ref"] == "RFI-012"
    assert rows[0]["occurred_at"] == "05/03/2026"
    assert rows[0]["status"] == "closed"
    assert "Can we add 3 GPOs?" in rows[0]["text"]
    assert "Yes proceed" in rows[0]["text"]
    # second row has a question but no response -> still ingested
    assert rows[1]["ref"] == "RFI-013"


def test_parse_rfi_csv_aliases_and_missing_number():
    csv = "no,title,query,answer\n,Latent rock,Was rock expected?,No it was not\n"
    rows = parse_rfi_csv(csv.encode())
    assert len(rows) == 1
    assert rows[0]["ref"] == "RFI-1"          # synthesised when number missing
    assert "Was rock expected?" in rows[0]["text"]


# -- endpoint --------------------------------------------------------------
class FakeStore:
    def __init__(self):
        self.puts: list[tuple[str, str]] = []

    def put(self, key, data):
        self.puts.append((key, data))
        return key


def test_upload_rfis_endpoint_creates_documents():
    user = User(id=uuid.uuid4(), email="ca@firm.com", password_hash="x", is_active=True)
    cid = uuid.uuid4()
    project = Project(id=uuid.uuid4(), company_id=cid, name="Tower A",
                      status=ProjectStatus.in_progress)
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid)
    store = FakeStore()
    # _load_project: execute(memberships).scalars().all() -> [membership]; get(Project) -> project
    session = FakeSession(results=[FakeResult(scalars=[membership])], get_obj=project)

    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_store] = lambda: store
    try:
        csv = ("rfi_number,subject,question,response,date_raised\n"
               "RFI-1,Extra works,Add GPOs?,Proceed,05/03/2026\n"
               "RFI-2,Rock,Expected?,No,06/03/2026\n").encode()
        resp = TestClient(app).post(f"/projects/{project.id}/rfis",
                                    files={"file": ("rfis.csv", csv, "text/csv")})
        assert resp.status_code == 200
        assert resp.json()["documents_added"] == 2
        assert len(store.puts) == 2                       # both RFIs stored
    finally:
        app.dependency_overrides.clear()
