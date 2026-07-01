"""Report generation (.15): build_report aggregation, PDF render, endpoints."""
import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

from app.auth.deps import get_current_user, get_db
from app.main import app
from app.models import (
    AnalysisJob,
    BasisQuality,
    ConfidenceBand,
    Evidence,
    Membership,
    Project,
    ProjectStatus,
    ReviewStatus,
    SourceType,
    User,
    ValueEstimate,
    Variation,
)
from app.reports_pdf import render_report_pdf
from app.services import reports as report_service
from tests.fakes import FakeResult, FakeSession


def _project(cid):
    return Project(id=uuid.uuid4(), company_id=cid, name="Tower A", state="NSW",
                   status=ProjectStatus.completed)


def _variation(cid, pid, amount):
    v = Variation(id=uuid.uuid4(), company_id=cid, project_id=pid, job_id=uuid.uuid4(),
                  title="Extra GPOs", description="Out of scope.",
                  confidence_score=Decimal("0.82"), confidence_band=ConfidenceBand.high,
                  time_bar_risk=True, review_status=ReviewStatus.confirmed)
    ve = ValueEstimate(id=uuid.uuid4(), variation_id=v.id, amount=Decimal(str(amount)),
                       estimate_low=Decimal("3000"), estimate_high=Decimal("5000"),
                       currency="AUD", basis_quality=BasisQuality.rate_card,
                       confidence=ConfidenceBand.medium)
    ev = Evidence(id=uuid.uuid4(), variation_id=v.id, source_type=SourceType.email)
    return v, ve, ev


def _build_session(cid, project, v, ve, ev):
    job = AnalysisJob(id=uuid.uuid4(), company_id=cid, project_id=project.id,
                      request_id=uuid.uuid4())
    job.baseline = {"sop_regime": "NSW SOP Act 1999", "notice_clause": "Cl 36.1",
                    "time_bar_days": 20, "inclusions": [], "exclusions": []}
    # build_report query order: job, variations, value_estimates, evidence
    return FakeSession(results=[
        FakeResult(scalar=job),
        FakeResult(scalars=[v]),
        FakeResult(scalars=[ve]),
        FakeResult(scalars=[ev]),
    ])


# -- build_report ----------------------------------------------------------
def test_build_report_aggregates_totals_and_baseline():
    cid = uuid.uuid4()
    project = _project(cid)
    v, ve, ev = _variation(cid, project.id, 4200)
    session = _build_session(cid, project, v, ve, ev)
    report = report_service.build_report(session, company_id=cid, project=project)

    assert report["project"]["name"] == "Tower A"
    assert report["baseline"]["sop_regime"] == "NSW SOP Act 1999"
    assert report["summary"]["variation_count"] == 1
    assert report["summary"]["recoverable_total"] == 4200.0
    assert report["summary"]["time_bar_at_risk"] == 1
    item = report["variations"][0]
    assert item["confidence_band"] == "high"
    assert item["value"]["estimate_high"] == 5000.0
    assert item["evidence_count"] == 1


# -- PDF render ------------------------------------------------------------
def test_render_report_pdf_returns_pdf_bytes():
    report = {
        "project": {"name": "Tower A", "state": "NSW", "status": "completed"},
        "baseline": {"sop_regime": "NSW SOP Act 1999", "notice_clause": "Cl 36.1",
                     "time_bar_days": 20},
        "generated_at": "2026-06-28T00:00:00Z", "status_filter": "confirmed",
        "summary": {"variation_count": 1, "recoverable_total": 4200.0,
                    "currency": "AUD", "time_bar_at_risk": 1},
        "variations": [{"title": "Extra GPOs", "confidence_score": 0.82,
                        "confidence_band": "high", "time_bar_risk": True,
                        "evidence_count": 1,
                        "value": {"amount": 4200.0, "basis_quality": "rate_card"}}],
    }
    pdf = render_report_pdf(report)
    assert isinstance(pdf, bytes) and pdf[:5] == b"%PDF-"
    assert len(pdf) > 1000


def test_render_report_pdf_escapes_hostile_free_text():
    """Project name / variation title can contain reportlab markup or malformed
    tags (via user input or LLM output derived from an uploaded document) —
    must not break Paragraph's mini-XML parser or inject unintended markup."""
    report = {
        "project": {"name": "<b>Evil</b> & <script>x</script> <unclosed",
                    "state": "NSW", "status": "completed"},
        "baseline": None,
        "generated_at": "2026-06-28T00:00:00Z", "status_filter": "confirmed",
        "summary": {"variation_count": 1, "recoverable_total": 100.0,
                    "currency": "AUD", "time_bar_at_risk": 0},
        "variations": [{"title": "<font size=\"999\">huge</font> <b>bold & broken",
                        "confidence_score": 0.5, "confidence_band": "medium",
                        "time_bar_risk": False, "evidence_count": 0, "value": {}}],
    }
    # Would raise inside reportlab's paraparser if the hostile markup weren't
    # escaped first — a clean render is itself proof the fix works.
    pdf = render_report_pdf(report)
    assert isinstance(pdf, bytes) and pdf[:5] == b"%PDF-"


# -- endpoints -------------------------------------------------------------
def _client(session, user):
    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def _user():
    return User(id=uuid.uuid4(), email="ca@firm.com", password_hash="x", is_active=True)


def test_report_json_endpoint():
    user = _user()
    cid = uuid.uuid4()
    project = _project(cid)
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid)
    v, ve, ev = _variation(cid, project.id, 4200)
    # _load: session.get(Project)->project ; ensure_member execute->membership
    # then build_report: job, variations, values, evidence
    job = AnalysisJob(id=uuid.uuid4(), company_id=cid, project_id=project.id,
                      request_id=uuid.uuid4())
    job.baseline = {"inclusions": [], "exclusions": []}
    session = FakeSession(results=[
        FakeResult(scalar=membership),
        FakeResult(scalar=job),
        FakeResult(scalars=[v]),
        FakeResult(scalars=[ve]),
        FakeResult(scalars=[ev]),
    ], get_obj=project)
    resp = _client(session, user).get(f"/projects/{project.id}/report")
    assert resp.status_code == 200
    assert resp.json()["summary"]["recoverable_total"] == 4200.0


def test_report_pdf_endpoint_content_type():
    user = _user()
    cid = uuid.uuid4()
    project = _project(cid)
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid)
    v, ve, ev = _variation(cid, project.id, 4200)
    job = AnalysisJob(id=uuid.uuid4(), company_id=cid, project_id=project.id,
                      request_id=uuid.uuid4())
    job.baseline = {"inclusions": [], "exclusions": []}
    session = FakeSession(results=[
        FakeResult(scalar=membership),
        FakeResult(scalar=job),
        FakeResult(scalars=[v]),
        FakeResult(scalars=[ve]),
        FakeResult(scalars=[ev]),
    ], get_obj=project)
    resp = _client(session, user).get(f"/projects/{project.id}/report.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"
