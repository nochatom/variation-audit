"""Dashboard aggregation (.16): org overview + project rollups + endpoints."""
import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

from app.auth.deps import get_current_user, get_db
from app.main import app
from app.models import (
    AnalysisJob,
    ConfidenceBand,
    JobStatus,
    Membership,
    Project,
    ProjectStatus,
    ReviewStatus,
    User,
    ValueEstimate,
    Variation,
)
from app.services import dashboard as dashboard_service
from tests.fakes import FakeResult, FakeSession


def _project(cid, name="Tower A"):
    return Project(id=uuid.uuid4(), company_id=cid, name=name, state="NSW",
                   status=ProjectStatus.in_progress, contract_text="...")


def _variation(cid, pid, status, time_bar=False):
    return Variation(id=uuid.uuid4(), company_id=cid, project_id=pid, job_id=uuid.uuid4(),
                     title="V", confidence_score=Decimal("0.8"),
                     confidence_band=ConfidenceBand.high, review_status=status,
                     time_bar_risk=time_bar)


def _value(v, amount):
    return ValueEstimate(id=uuid.uuid4(), variation_id=v.id, amount=Decimal(str(amount)),
                         currency="AUD", confidence=ConfidenceBand.medium)


# -- org overview ----------------------------------------------------------
def test_org_overview_aggregates_by_project():
    cid = uuid.uuid4()
    p = _project(cid)
    v1 = _variation(cid, p.id, ReviewStatus.confirmed, time_bar=True)
    v2 = _variation(cid, p.id, ReviewStatus.pending)
    confirmed_val = _value(v1, 4200)
    session = FakeSession(results=[
        FakeResult(scalars=[p]),               # projects
        FakeResult(scalars=[v1, v2]),          # variations
        FakeResult(scalars=[confirmed_val]),   # confirmed value estimates
    ])
    out = dashboard_service.org_overview(session, cid)
    assert out["totals"]["projects"] == 1
    assert out["totals"]["pending"] == 1 and out["totals"]["confirmed"] == 1
    assert out["totals"]["recoverable_confirmed"] == 4200.0
    row = out["projects"][0]
    assert row["counts"] == {"pending": 1, "confirmed": 1, "rejected": 0, "total": 2}
    assert row["recoverable_confirmed"] == 4200.0
    assert row["time_bar_at_risk"] == 1
    assert "review_queue" in row["links"]


# -- project dashboard -----------------------------------------------------
def test_project_dashboard():
    cid = uuid.uuid4()
    p = _project(cid)
    v1 = _variation(cid, p.id, ReviewStatus.confirmed, time_bar=True)
    job = AnalysisJob(id=uuid.uuid4(), company_id=cid, project_id=p.id,
                      request_id=uuid.uuid4(), recoverable_total=Decimal("9000"),
                      status=JobStatus.succeeded)
    session = FakeSession(results=[
        FakeResult(scalars=[v1]),              # variations
        FakeResult(scalars=[_value(v1, 4200)]),  # confirmed values
        FakeResult(scalar=job),                # latest job
        FakeResult(scalars=[]),                # documents
    ])
    out = dashboard_service.project_dashboard(session, cid, p)
    assert out["counts"]["confirmed"] == 1
    assert out["recoverable_confirmed"] == 4200.0
    assert out["time_bar_at_risk"] == 1
    assert out["document_count"] == 0
    assert out["latest_job"]["recoverable_total"] == 9000.0
    assert out["links"]["report_pdf"].endswith("/report.pdf")


# -- endpoints -------------------------------------------------------------
def _client(session, user):
    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_org_dashboard_endpoint():
    user = User(id=uuid.uuid4(), email="a@f.com", password_hash="x", is_active=True)
    cid = uuid.uuid4()
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid)
    p = _project(cid)
    session = FakeSession(results=[
        FakeResult(scalar=membership),         # ensure_member
        FakeResult(scalars=[p]),               # projects
        FakeResult(scalars=[]),                # variations
        FakeResult(scalars=[]),                # confirmed values
    ])
    resp = _client(session, user).get(f"/dashboard?company_id={cid}")
    assert resp.status_code == 200
    assert resp.json()["totals"]["projects"] == 1
