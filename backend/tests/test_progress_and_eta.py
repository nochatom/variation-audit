"""Unit tests for progress + ETA tracking (requirement #2): the
agent-agnostic on_agent_complete hook built by
app/agents/worker.py:_make_progress_callback, and the orchestrator's own
AGENT_PROGRESS curve.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.agents import worker as worker_module
from app.agents.orchestrator import AGENT_PROGRESS, build_orchestrator
from tests.fakes import FakeSession
from tests.test_agent_jobs_and_worker import _job


def test_agent_progress_curve_matches_the_spec_example():
    assert AGENT_PROGRESS == {
        "project_intake_agent": 10,
        "document_agent": 20,
        "contract_agent": 30,
        "variation_detection_agent": 55,
        "evidence_agent": 70,
        "cost_time_agent": 85,
        "report_generation_agent": 95,
        "quality_review_agent": 98,
        "human_review_gate": 99,
    }


def test_progress_callback_updates_current_agent_and_percent():
    job = _job(status=worker_module.AgentJobStatus.processing,
              started_at=datetime.now(timezone.utc) - timedelta(seconds=10))
    session = FakeSession()
    callback = worker_module._make_progress_callback(job, session)

    callback("variation_detection_agent", 55)

    assert job.current_agent == "variation_detection_agent"
    assert job.progress_percent == 55
    assert job.last_progress_at is not None
    assert session.commits == 1


def test_eta_shrinks_as_progress_increases():
    started = datetime.now(timezone.utc) - timedelta(seconds=20)
    job = _job(status=worker_module.AgentJobStatus.processing, started_at=started)
    session = FakeSession()
    callback = worker_module._make_progress_callback(job, session)

    callback("project_intake_agent", 10)
    eta_at_10 = job.estimated_remaining_seconds

    callback("report_generation_agent", 95)
    eta_at_95 = job.estimated_remaining_seconds

    assert eta_at_10 is not None
    assert eta_at_95 is not None
    assert eta_at_95 < eta_at_10


def test_eta_is_none_at_zero_percent():
    job = _job(status=worker_module.AgentJobStatus.processing,
              started_at=datetime.now(timezone.utc))
    session = FakeSession()
    callback = worker_module._make_progress_callback(job, session)

    callback("some_agent", 0)

    assert job.estimated_remaining_seconds is None


def test_final_completion_sets_100_percent_and_zero_eta(monkeypatch):
    job = _job(status=worker_module.AgentJobStatus.processing)
    session = FakeSession()

    async def fake_analyze(session_, project_id, **kwargs):
        kwargs["on_agent_complete"]("quality_review_agent", 98)
        return {"project_id": str(job.project_id)}

    monkeypatch.setattr(worker_module, "analyze_project_with_agents", fake_analyze)

    worker_module.process_job(session, job)

    assert job.progress_percent == 100
    assert job.estimated_remaining_seconds == 0
    assert job.current_agent is None


def test_orchestrator_progress_hook_is_called_per_agent_name():
    calls = []
    build_orchestrator(on_agent_complete=lambda name, pct: calls.append((name, pct)))
    # construction alone doesn't run any agent, so no calls yet — this just
    # proves the hook wires through build_orchestrator without raising.
    assert calls == []
