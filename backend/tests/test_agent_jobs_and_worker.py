"""Unit tests for the async execution layer: app/agents/jobs.py (enqueue)
and app/agents/worker.py (claim / process / stale-job recovery).

Uses FakeSession (tests/fakes.py) — same DB-less pattern as the existing
job_worker tests — plus a monkeypatched analyze_project_with_agents so
process_job() tests never make a real LLM call.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.agents import worker as worker_module
from app.agents.errors import AIAuthError
from app.agents.jobs import enqueue_agent_analysis
from app.models import AgentAnalysisJob, AgentJobStatus
from tests.fakes import FakeResult, FakeSession


def _job(**overrides) -> AgentAnalysisJob:
    defaults = dict(
        id=uuid.uuid4(), company_id=uuid.uuid4(), project_id=uuid.uuid4(),
        created_by=uuid.uuid4(), status=AgentJobStatus.queued, progress_percent=0,
    )
    defaults.update(overrides)
    return AgentAnalysisJob(**defaults)


# --------------------------------------------------------------------------
# jobs.py
# --------------------------------------------------------------------------
def test_enqueue_agent_analysis_creates_queued_job():
    session = FakeSession()
    company_id, project_id, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    job = enqueue_agent_analysis(session, company_id=company_id, project_id=project_id, created_by=user_id)

    assert job.status == AgentJobStatus.queued
    assert job.progress_percent == 0
    assert job.company_id == company_id
    assert job.project_id == project_id
    assert session.commits == 1
    assert session.added_of(AgentAnalysisJob) == [job]


# --------------------------------------------------------------------------
# worker.py — claiming
# --------------------------------------------------------------------------
def test_claim_one_marks_job_processing():
    job = _job(status=AgentJobStatus.queued)
    session = FakeSession(results=[FakeResult(scalar=job)])

    claimed = worker_module.claim_one(session, "worker-1")

    assert claimed is job
    assert job.status == AgentJobStatus.processing
    assert job.worker_id == "worker-1"
    assert job.started_at is not None
    assert job.heartbeat_at is not None
    assert job.last_progress_at is not None
    assert session.commits == 1


def test_claim_one_returns_none_when_queue_empty():
    session = FakeSession(results=[FakeResult(scalar=None)])
    assert worker_module.claim_one(session, "worker-1") is None


# --------------------------------------------------------------------------
# worker.py — stale-job recovery
# --------------------------------------------------------------------------
def test_reclaim_stale_jobs_fails_stuck_jobs():
    stale = _job(status=AgentJobStatus.processing)
    session = FakeSession(results=[FakeResult(scalars=[stale])])

    count = worker_module.reclaim_stale_jobs(session, stale_after=timedelta(minutes=30))

    assert count == 1
    assert stale.status == AgentJobStatus.failed
    assert stale.error_code == "WORKER_STALLED"
    assert stale.completed_at is not None
    assert session.commits == 1


def test_reclaim_stale_jobs_noop_when_none_stale():
    session = FakeSession(results=[FakeResult(scalars=[])])

    count = worker_module.reclaim_stale_jobs(session, stale_after=timedelta(minutes=30))

    assert count == 0
    assert session.commits == 0


# --------------------------------------------------------------------------
# worker.py — processing
# --------------------------------------------------------------------------
def test_process_job_success_persists_result_and_full_progress(monkeypatch):
    job = _job(status=AgentJobStatus.processing)
    session = FakeSession()
    expected_result = {"project_id": str(job.project_id), "requires_human_review": False}

    async def fake_analyze(session_, project_id, **kwargs):
        kwargs["on_agent_complete"]("report_generation_agent", 95)
        return expected_result

    monkeypatch.setattr(worker_module, "analyze_project_with_agents", fake_analyze)

    worker_module.process_job(session, job)

    assert job.status == AgentJobStatus.completed
    assert job.result == expected_result
    assert job.progress_percent == 100
    assert job.current_agent is None
    assert job.completed_at is not None
    # one commit from the on_agent_complete progress callback, one on completion
    assert session.commits == 2


def test_process_job_ai_provider_error_marks_failed_with_code(monkeypatch):
    job = _job(status=AgentJobStatus.processing)
    session = FakeSession()

    async def fake_analyze(session_, project_id, **kwargs):
        raise AIAuthError("bad key", provider="openai", model="x")

    monkeypatch.setattr(worker_module, "analyze_project_with_agents", fake_analyze)

    worker_module.process_job(session, job)

    assert job.status == AgentJobStatus.failed
    assert job.error_code == "AI_AUTH_ERROR"


def test_process_job_intake_rejection_marks_failed_with_code(monkeypatch):
    job = _job(status=AgentJobStatus.processing)
    session = FakeSession()

    async def fake_analyze(session_, project_id, **kwargs):
        raise RuntimeError("project has no contract_text")

    monkeypatch.setattr(worker_module, "analyze_project_with_agents", fake_analyze)

    worker_module.process_job(session, job)

    assert job.status == AgentJobStatus.failed
    assert job.error_code == "AGENT_INTAKE_REJECTED"


def test_process_job_unexpected_exception_marks_failed_with_generic_code(monkeypatch):
    job = _job(status=AgentJobStatus.processing)
    session = FakeSession()

    async def fake_analyze(session_, project_id, **kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(worker_module, "analyze_project_with_agents", fake_analyze)

    worker_module.process_job(session, job)

    assert job.status == AgentJobStatus.failed
    assert job.error_code == "AGENT_PIPELINE_ERROR"


# --------------------------------------------------------------------------
# worker.py — full run_once flow (claim -> process -> persist)
# --------------------------------------------------------------------------
def test_run_once_claims_and_processes_a_job(monkeypatch):
    job = _job(status=AgentJobStatus.queued)
    session = FakeSession(results=[FakeResult(scalars=[]), FakeResult(scalar=job)])

    async def fake_analyze(session_, project_id, **kwargs):
        return {"project_id": str(job.project_id)}

    monkeypatch.setattr(worker_module, "analyze_project_with_agents", fake_analyze)

    def session_factory():
        return _NullContextSession(session)

    handled = worker_module.run_once(session_factory)

    assert handled is True
    assert job.status == AgentJobStatus.completed


def test_run_once_returns_false_when_queue_empty():
    session = FakeSession(results=[FakeResult(scalars=[]), FakeResult(scalar=None)])

    def session_factory():
        return _NullContextSession(session)

    assert worker_module.run_once(session_factory) is False


class _NullContextSession:
    """Wraps a FakeSession so `with session_factory() as session:` works."""

    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *exc):
        return False
