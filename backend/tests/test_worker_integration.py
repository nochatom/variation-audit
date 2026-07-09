"""Integration tests against a real local Postgres (requirement #5:
concurrent load testing, plus the heartbeat-vs-fixed-timeout filter from
requirement #1).

FakeSession doesn't evaluate SQL WHERE clauses, so the actual FOR UPDATE
SKIP LOCKED concurrency guarantee and the heartbeat staleness filter can
only be proven against a real database. Skipped automatically if no
reachable Postgres is configured (VA_DATABASE_URL) — CI environments
without a database still pass the rest of the suite.
"""
from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.agents import worker as worker_module
from app.models import AgentAnalysisJob, AgentJobStatus, Organization, Project

try:
    from app.db import engine, session_factory
    with engine.connect() as _conn:
        _conn.execute(text("SELECT 1"))
    _DB_AVAILABLE = True
except Exception:
    _DB_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _DB_AVAILABLE, reason="no reachable Postgres configured (VA_DATABASE_URL)"
)


@pytest.fixture
def project_ref():
    with session_factory() as session:
        org = Organization(id=uuid.uuid4(), name="Load Test Org")
        session.add(org)
        session.flush()
        proj = Project(id=uuid.uuid4(), company_id=org.id, name="Load Test Project",
                       contract_text="contract text", scope_text="scope text", state="NSW")
        session.add(proj)
        session.commit()
        company_id, project_id = org.id, proj.id

    yield company_id, project_id

    with session_factory() as session:
        session.execute(text("DELETE FROM agent_analysis_jobs WHERE project_id = :p"), {"p": str(project_id)})
        session.execute(text("DELETE FROM projects WHERE id = :p"), {"p": str(project_id)})
        session.execute(text("DELETE FROM organizations WHERE id = :c"), {"c": str(company_id)})
        session.commit()


def _create_queued_jobs(company_id, project_id, n):
    ids = []
    with session_factory() as session:
        for _ in range(n):
            job = AgentAnalysisJob(id=uuid.uuid4(), company_id=company_id, project_id=project_id,
                                   status=AgentJobStatus.queued, progress_percent=0)
            session.add(job)
            ids.append(job.id)
        session.commit()
    return ids


# --------------------------------------------------------------------------
# Concurrent claim safety (requirement #5)
# --------------------------------------------------------------------------
def test_ten_concurrent_workers_claim_all_jobs_exactly_once(project_ref):
    company_id, project_id = project_ref
    job_ids = _create_queued_jobs(company_id, project_id, 10)

    def worker_loop(worker_index):
        worker_id = f"loadtest-worker-{worker_index}"
        claimed = []
        with session_factory() as session:
            while True:
                job = worker_module.claim_one(session, worker_id)
                if job is None:
                    break
                claimed.append(job.id)
        return worker_id, claimed

    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(worker_loop, range(10)))
    elapsed = time.monotonic() - t0

    claimed_by: dict = {}
    conflicts = []
    total_claimed = []
    for worker_id, claimed in results:
        for job_id in claimed:
            if job_id in claimed_by:
                conflicts.append((job_id, claimed_by[job_id], worker_id))
            claimed_by[job_id] = worker_id
        total_claimed.extend(claimed)

    assert conflicts == [], "a job was claimed by more than one worker — SKIP LOCKED failed"
    assert sorted(total_claimed) == sorted(job_ids)
    assert len(set(total_claimed)) == 10

    with session_factory() as session:
        statuses = session.execute(
            text("SELECT status FROM agent_analysis_jobs WHERE project_id = :p"), {"p": str(project_id)}
        ).scalars().all()
    assert all(s == "processing" for s in statuses)

    throughput = 10 / elapsed if elapsed > 0 else float("inf")
    print(f"\n[load test] 10 jobs / 10 concurrent workers: {elapsed*1000:.1f}ms total, "
          f"0 double-claims, throughput={throughput:.1f} claims/s")


def test_failures_in_one_job_do_not_affect_others(project_ref, monkeypatch):
    company_id, project_id = project_ref
    job_ids = _create_queued_jobs(company_id, project_id, 5)
    failing_job_id = job_ids[2]

    async def fake_analyze(session_, project_id_, **kwargs):
        if kwargs.get("job_id") == str(failing_job_id):
            raise RuntimeError("simulated failure — must not affect other jobs")
        kwargs["on_agent_complete"]("report_generation_agent", 95)
        return {"project_id": project_id_}

    monkeypatch.setattr(worker_module, "analyze_project_with_agents", fake_analyze)

    worker_id = "loadtest-sequential"
    with session_factory() as session:
        for _ in range(5):
            job = worker_module.claim_one(session, worker_id)
            worker_module.process_job(session, job, worker_id)

    with session_factory() as session:
        rows = session.execute(
            text("SELECT id, status FROM agent_analysis_jobs WHERE project_id = :p"), {"p": str(project_id)}
        ).all()
    statuses = {row.id: row.status for row in rows}

    assert statuses[failing_job_id] == "failed"
    for job_id in job_ids:
        if job_id != failing_job_id:
            assert statuses[job_id] == "completed"


# --------------------------------------------------------------------------
# Heartbeat-based recovery, not a fixed timeout (requirement #1)
# --------------------------------------------------------------------------
def test_reclaim_stale_jobs_recovers_only_truly_abandoned_ones(project_ref):
    company_id, project_id = project_ref
    active_id, stale_id = _create_queued_jobs(company_id, project_id, 2)

    now = datetime.now(timezone.utc)
    with session_factory() as session:
        active = session.get(AgentAnalysisJob, active_id)
        active.status = AgentJobStatus.processing
        active.worker_id = "still-alive"
        active.heartbeat_at = now

        stale = session.get(AgentAnalysisJob, stale_id)
        stale.status = AgentJobStatus.processing
        stale.worker_id = "long-dead"
        stale.heartbeat_at = now - timedelta(minutes=10)

        session.commit()

    with session_factory() as session:
        count = worker_module.reclaim_stale_jobs(session, stale_after=timedelta(minutes=3))
    assert count == 1

    with session_factory() as session:
        active = session.get(AgentAnalysisJob, active_id)
        stale = session.get(AgentAnalysisJob, stale_id)
        assert active.status == AgentJobStatus.processing, "an actively-heartbeating job must not be reclaimed"
        assert stale.status == AgentJobStatus.failed
        assert stale.error_code == "WORKER_STALLED"
