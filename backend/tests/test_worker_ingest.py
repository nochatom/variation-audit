"""Worker logic: claim_one, build_request, ingest_result — with fake sessions."""
import uuid

import pytest
from sqlalchemy.orm.exc import StaleDataError

from app.engine.schemas import (
    AnalysisResult,
    BaselineOut,
    EstimatedValueOut,
    EvidenceOut,
    JobPoll,
    VariationOut,
)
from app.models import (
    AnalysisJob,
    BasisQuality,
    Document,
    Evidence,
    JobStatus,
    Notification,
    Project,
    SourceType,
    ValueEstimate,
    Variation,
)
from app.worker.job_worker import build_request, claim_one, fail_job, ingest_result
import app.worker.job_worker as job_worker
from tests.fakes import FakeResult, FakeSession


def _job() -> AnalysisJob:
    j = AnalysisJob()
    j.id = uuid.uuid4()
    j.company_id = uuid.uuid4()
    j.project_id = uuid.uuid4()
    j.created_by = uuid.uuid4()
    j.request_id = uuid.uuid4()
    return j


# -- claim_one -------------------------------------------------------------
def test_claim_one_none_when_empty():
    session = FakeSession(results=[FakeResult(scalar=None)])
    assert claim_one(session) is None


def test_claim_one_marks_running():
    job = _job()
    job.status = JobStatus.queued
    session = FakeSession(results=[FakeResult(scalar=job)])
    out = claim_one(session)
    assert out is job
    assert job.status == JobStatus.running
    assert job.started_at is not None
    assert session.commits == 1


# -- build_request ---------------------------------------------------------
def test_build_request_maps_documents():
    docs = []
    for i in range(2):
        d = Document()
        d.id = uuid.uuid4()
        d.source_type = SourceType.rfi
        d.doc_timestamp = None
        d.source = f"s{i}"
        d.storage_key = f"k{i}"
        docs.append(d)
    project = Project()
    project.contract_text = "Install switchboard per E-01."
    project.scope_text = "Electrical fit-out."
    project.state = "NSW"
    session = FakeSession(results=[FakeResult(scalars=docs)], get_obj=project)

    class Loader:
        def load(self, key):
            return f"content::{key}"

    req = build_request(session, _job(), Loader())
    assert len(req.documents) == 2
    assert req.documents[0].content == "content::k0"
    assert req.documents[0].type == SourceType.rfi
    assert req.country == "AU"
    # v1.2: contract baseline inputs flow from the project
    assert req.contract_text == "Install switchboard per E-01."
    assert req.scope_text == "Electrical fit-out."
    assert req.state == "NSW"


# -- ingest_result ---------------------------------------------------------
def test_ingest_creates_rows_and_marks_succeeded():
    vid, did = str(uuid.uuid4()), str(uuid.uuid4())
    poll = JobPoll(
        job_id="ej-1",
        status=JobStatus.succeeded,
        engine_version="v1",
        result=AnalysisResult(
            project_id="p1",
            engine_version="v1",
            baseline=BaselineOut(inclusions_count=2, exclusions_count=1,
                                 notice_clause="Clause 36.1", time_bar_days=20,
                                 sop_regime="NSW SOP Act 1999"),
            recoverable_total=4200,
            time_bar_at_risk=1,
            variations=[
                VariationOut(
                    variation_id=vid,
                    title="Unclaimed extra works",
                    confidence_score=0.9,                       # -> band high
                    confidence_factors={"evidence": 0.66},
                    time_bar_risk=True,                          # AU SoP
                    evidence=[EvidenceOut(type=SourceType.email, source_document_id=did,
                                          reference="thread#12", quote="please proceed")],
                    estimated_value=EstimatedValueOut(
                        amount=4200, estimate_low=3000, estimate_high=5000, currency="AUD",
                        basis_quality=BasisQuality.rate_card, valuation_confidence_score=0.6),
                )
            ],
        ),
    )
    job, session = _job(), FakeSession()
    ingest_result(session, job, poll)

    assert job.status == JobStatus.succeeded
    assert job.finished_at is not None
    assert job.engine_version == "v1"
    # v1.2 job-level rollups
    assert job.recoverable_total == 4200
    assert job.time_bar_at_risk == 1
    assert job.baseline["sop_regime"] == "NSW SOP Act 1999"

    variations = session.added_of(Variation)
    assert len(variations) == 1
    assert variations[0].confidence_band.value == "high"
    assert variations[0].time_bar_risk is True
    assert variations[0].confidence_factors == {"evidence": 0.66}
    assert len(session.added_of(Evidence)) == 1
    values = session.added_of(ValueEstimate)
    assert len(values) == 1
    assert values[0].confidence.value == "medium"
    assert values[0].estimate_low == 3000 and values[0].estimate_high == 5000
    assert values[0].basis_quality == BasisQuality.rate_card
    assert len(session.added_of(Notification)) == 1   # created_by set -> notified
    assert session.commits >= 1


def test_ingest_result_url_sets_ref_without_variations():
    poll = JobPoll(job_id="ej-1", status=JobStatus.succeeded, engine_version="v1",
                   result=None, result_url="https://s3/large-result.json")
    job, session = _job(), FakeSession()
    ingest_result(session, job, poll)
    assert job.result_ref == "https://s3/large-result.json"
    assert job.status == JobStatus.succeeded
    assert session.added_of(Variation) == []


# -- robustness: a failing job must never take the worker down --------------
def test_fail_job_survives_vanished_row():
    """If the job row was deleted under us, fail_job must roll back and return
    — not raise StaleDataError (which used to crash the whole worker loop)."""
    class StaleSession(FakeSession):
        def __init__(self):
            super().__init__()
            self.rolledback = 0

        def commit(self):
            raise StaleDataError("UPDATE expected 1 row; 0 matched")

        def rollback(self):
            self.rolledback += 1

    job = _job()
    job.created_by = None  # no notification recipient -> _notify is a no-op
    session = StaleSession()
    fail_job(session, job, "INTERNAL", "engine disconnected", retryable=True)  # must NOT raise
    assert session.rolledback == 1


def test_run_forever_survives_iteration_crash(monkeypatch):
    """One poisoned iteration must not kill the loop — the worker keeps going,
    otherwise every later job is stuck 'queued' forever."""
    calls = {"n": 0}

    def fake_run_once(_sf, _c, _l):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom in iteration 1")  # simulate an unexpected crash
        return False  # idle thereafter

    monkeypatch.setattr(job_worker, "run_once", fake_run_once)

    sleeps = {"n": 0}

    def fake_sleep(_):
        sleeps["n"] += 1
        if sleeps["n"] >= 2:
            raise KeyboardInterrupt  # break the infinite loop for the test

    with pytest.raises(KeyboardInterrupt):
        job_worker.run_forever(None, None, None, sleep=fake_sleep)
    # Reached a 2nd iteration => it survived the iteration-1 crash.
    assert calls["n"] >= 2
