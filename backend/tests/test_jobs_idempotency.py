"""enqueue_analysis idempotency (decision .21.4)."""
import uuid
from datetime import datetime, timezone

import pytest

from app.models import AnalysisJob, JobStatus
from app.services.jobs import IdempotencyConflict, enqueue_analysis
from tests.fakes import FakeResult, FakeSession


def test_enqueue_new_job_is_queued():
    session = FakeSession(results=[FakeResult(scalar=None)])
    job = enqueue_analysis(
        session, company_id=uuid.uuid4(), project_id=uuid.uuid4(), created_by=uuid.uuid4()
    )
    assert job.status == JobStatus.queued
    assert job.request_id is not None
    assert job in session.added
    assert session.commits == 1


def test_enqueue_idempotent_replay_returns_existing():
    cid, pid, rid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    existing = AnalysisJob()
    existing.company_id, existing.project_id, existing.request_id = cid, pid, rid
    existing.created_at = datetime.now(timezone.utc)
    existing.status = JobStatus.queued
    session = FakeSession(results=[FakeResult(scalar=existing)])

    job = enqueue_analysis(session, company_id=cid, project_id=pid, request_id=rid)
    assert job is existing
    assert existing not in session.added   # no duplicate row
    assert session.commits == 0


def test_enqueue_conflict_on_cross_project_reuse():
    cid, rid = uuid.uuid4(), uuid.uuid4()
    existing = AnalysisJob()
    existing.company_id, existing.project_id, existing.request_id = cid, uuid.uuid4(), rid
    existing.created_at = datetime.now(timezone.utc)
    session = FakeSession(results=[FakeResult(scalar=existing)])

    with pytest.raises(IdempotencyConflict):
        enqueue_analysis(session, company_id=cid, project_id=uuid.uuid4(), request_id=rid)
