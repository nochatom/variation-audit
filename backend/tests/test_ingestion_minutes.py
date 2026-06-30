"""Meeting minutes ingestion (.7): register CSV parser + upload endpoint."""
import uuid

from fastapi.testclient import TestClient

from app.auth.deps import get_current_user, get_db
from app.main import app
from app.models import Membership, Project, ProjectStatus, User
from app.parsing import parse_meeting_minutes_csv
from app.storage import get_store
from tests.fakes import FakeResult, FakeSession


# -- parser ----------------------------------------------------------------
def test_parse_meeting_minutes_basic():
    csv = (
        "item,meeting_date,topic,discussion,decision,action,owner,status\n"
        "1,05/03/2026,Latent conditions,Rock found below RL,Proceed with extra excavation,"
        "Price the variation,QS,open\n"
        ",,,,,,,\n"  # blank -> skipped
        "2,05/03/2026,Programme,Slip due to weather,,Update programme,PM,open\n"
    )
    rows = parse_meeting_minutes_csv(csv.encode())
    assert len(rows) == 2
    assert rows[0]["ref"] == "1"
    assert rows[0]["occurred_at"] == "05/03/2026"
    assert "Latent conditions" in rows[0]["text"]
    assert "Decision: Proceed with extra excavation" in rows[0]["text"]
    assert "Action: Price the variation" in rows[0]["text"]
    assert "Owner: QS" in rows[0]["text"]


def test_parse_meeting_minutes_aliases_and_missing_number():
    csv = "subject,minute,resolution\nScope change,Client wants atrium glazing,Agreed to proceed\n"
    rows = parse_meeting_minutes_csv(csv.encode())
    assert len(rows) == 1
    assert rows[0]["ref"] == "MIN-1"
    assert "Client wants atrium glazing" in rows[0]["text"]
    assert "Decision: Agreed to proceed" in rows[0]["text"]


# -- endpoint --------------------------------------------------------------
class FakeStore:
    def __init__(self):
        self.puts: list[tuple[str, str]] = []

    def put(self, key, data):
        self.puts.append((key, data))
        return key


def test_upload_meeting_minutes_endpoint():
    user = User(id=uuid.uuid4(), email="ca@firm.com", password_hash="x", is_active=True)
    cid = uuid.uuid4()
    project = Project(id=uuid.uuid4(), company_id=cid, name="Tower A",
                      status=ProjectStatus.in_progress)
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid)
    store = FakeStore()
    session = FakeSession(results=[FakeResult(scalars=[membership])], get_obj=project)

    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_store] = lambda: store
    try:
        csv = ("item,meeting_date,topic,decision\n"
               "1,05/03/2026,Latent conditions,Proceed with extra works\n"
               "2,05/03/2026,Finishes,Upgrade approved\n").encode()
        resp = TestClient(app).post(f"/projects/{project.id}/meeting-minutes",
                                    files={"file": ("minutes.csv", csv, "text/csv")})
        assert resp.status_code == 200
        assert resp.json()["documents_added"] == 2
        assert len(store.puts) == 2
    finally:
        app.dependency_overrides.clear()
