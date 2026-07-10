"""Background worker for the agent scaffold's AgentAnalysisJob queue.

Same DB-backed `FOR UPDATE SKIP LOCKED` claim pattern as
app/worker/job_worker.py (the production engine-pipeline worker) — this is
a second, independent poll loop over a separate table, run as its own
process. The worker's only job is execution lifecycle: claim a row, run the
existing Root Orchestrator via app/agents/run.py, persist heartbeat/
progress/ETA/LLM-metrics/result/error. It does not know how any agent works
internally — "worker only manages execution lifecycle," not agent logic.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agents import circuit_breaker, provider_health
from app.agents.errors import AIProviderError
from app.agents.run import analyze_project_with_agents
from app.models import AgentAnalysisJob, AgentJobStatus

logger = logging.getLogger("app.agents.worker")

# Heartbeat-based recovery (requirement: "do not rely only on a fixed
# 30-minute timeout"). Refreshed every DEFAULT_HEARTBEAT_INTERVAL_S while a
# job is being worked; a job is only reclaimed once its heartbeat has
# genuinely gone silent for DEFAULT_HEARTBEAT_STALE_AFTER — several
# multiples of the refresh interval, so a slow-but-alive worker (e.g. mid a
# 120s NVIDIA NIM cold-start call) is never mistaken for a dead one.
DEFAULT_HEARTBEAT_INTERVAL_S = 45.0
DEFAULT_HEARTBEAT_STALE_AFTER = timedelta(minutes=3)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def generate_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


# --------------------------------------------------------------------------
# Claiming
# --------------------------------------------------------------------------
def claim_one(session: Session, worker_id: str) -> AgentAnalysisJob | None:
    """Atomically claim the oldest queued job. Concurrency-safe across workers."""
    job = session.execute(
        select(AgentAnalysisJob)
        .where(AgentAnalysisJob.status == AgentJobStatus.queued)
        .order_by(AgentAnalysisJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if job is None:
        return None
    now = _now()
    job.status = AgentJobStatus.processing
    job.worker_id = worker_id
    job.started_at = now
    job.heartbeat_at = now
    job.last_progress_at = now
    session.commit()
    return job


def record_heartbeat(session: Session, job_id: uuid.UUID, worker_id: str) -> bool:
    """Refresh heartbeat_at, only if `worker_id` still owns the job (still
    PROCESSING and not reclaimed out from under it). Returns whether the
    heartbeat was actually recorded."""
    job = session.execute(
        select(AgentAnalysisJob).where(
            AgentAnalysisJob.id == job_id,
            AgentAnalysisJob.worker_id == worker_id,
            AgentAnalysisJob.status == AgentJobStatus.processing,
        ).with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if job is None:
        return False
    job.heartbeat_at = _now()
    session.commit()
    return True


async def _heartbeat_loop(session_factory, job_id: uuid.UUID, worker_id: str, interval_s: float) -> None:
    """Runs alongside analyze_project_with_agents, refreshing heartbeat_at
    on its own short-lived session (never the session tools/agents are
    using) so a long single-agent LLM call doesn't look like a dead worker.
    Cancelled by _process_job_async once the run finishes either way."""
    while True:
        await asyncio.sleep(interval_s)
        try:
            with session_factory() as hb_session:
                still_owned = record_heartbeat(hb_session, job_id, worker_id)
            if not still_owned:
                logger.warning("job.heartbeat.lost_ownership",
                               extra={"job_id": str(job_id), "worker_id": worker_id})
        except Exception:  # noqa: BLE001 - a heartbeat failure must never kill the run
            logger.exception("job.heartbeat.error", extra={"job_id": str(job_id)})


def reclaim_stale_jobs(
    session: Session, stale_after: timedelta = DEFAULT_HEARTBEAT_STALE_AFTER
) -> int:
    """Fail-and-recover jobs whose heartbeat has genuinely gone silent.

    Keys off heartbeat_at (refreshed every ~45s by the owning worker), not
    a fixed wall-clock job-age timeout — a job legitimately taking a long
    time (multiple agents, each with a generous LLM timeout) is never
    reclaimed as long as its worker keeps heartbeating. Only a worker
    that's actually died (crashed, OOM-killed, host recycled) stops
    refreshing heartbeat_at, which is what this now detects.
    """
    cutoff = _now() - stale_after
    stale_jobs = session.execute(
        select(AgentAnalysisJob).where(
            AgentAnalysisJob.status == AgentJobStatus.processing,
            or_(AgentAnalysisJob.heartbeat_at.is_(None), AgentAnalysisJob.heartbeat_at < cutoff),
        ).with_for_update(skip_locked=True)
    ).scalars().all()

    for job in stale_jobs:
        logger.warning("job.reclaimed_stale", extra={
            "job_id": str(job.id), "worker_id": job.worker_id,
            "stale_after_s": stale_after.total_seconds(),
        })
        job.status = AgentJobStatus.failed
        job.error_code = "WORKER_STALLED"
        job.error_message = (
            f"heartbeat stale beyond {stale_after} — the worker that claimed "
            "this job likely crashed; re-trigger analysis to retry"
        )
        job.completed_at = _now()

    if stale_jobs:
        session.commit()
    return len(stale_jobs)


# --------------------------------------------------------------------------
# Processing one job
# --------------------------------------------------------------------------
def fail_job(session: Session, job: AgentAnalysisJob, code: str, message: str,
            llm_calls: list[dict] | None = None) -> None:
    job.status = AgentJobStatus.failed
    job.error_code = code
    job.error_message = message[:2000]
    job.completed_at = _now()
    if llm_calls is not None:
        job.llm_calls = llm_calls
    session.commit()


def _make_progress_callback(job: AgentAnalysisJob, session: Session):
    """Agent-agnostic progress hook handed to build_orchestrator() via
    run.py — updates current_agent/progress_percent/last_progress_at and a
    linear elapsed-time ETA. No agent (or the orchestrator) knows this
    exists; it's plain execution-lifecycle bookkeeping."""

    def on_agent_complete(agent_name: str, percent: int) -> None:
        now = _now()
        job.current_agent = agent_name
        job.progress_percent = percent
        job.last_progress_at = now
        if job.started_at and percent > 0:
            elapsed = (now - job.started_at).total_seconds()
            total_estimate = elapsed / (percent / 100)
            job.estimated_remaining_seconds = max(0, round(total_estimate - elapsed))
        else:
            job.estimated_remaining_seconds = None
        session.commit()

    return on_agent_complete


def _make_llm_call_sink(job: AgentAnalysisJob, llm_calls: list[dict], session_factory):
    """Per-call telemetry sink handed to ReliableLlm via run.py's
    on_llm_call — feeds provider_health.record() and
    circuit_breaker.record_outcome() (Phase 4's actual behavior change:
    the circuit breaker now receives real outcomes, including failures,
    for the first time).

    Deliberately best-effort: llm_calls.append() always happens first and
    unconditionally — the per-job metrics list worker.py already persisted
    before Phase 4 — so a telemetry failure can never cause a call to go
    unrecorded there. provider_health/circuit_breaker recording runs in
    its own short-lived session (never the job's own `session` — the same
    reasoning as the heartbeat loop: two "parallel" agent branches must
    never share one SQLAlchemy Session) and any exception is caught and
    logged, never re-raised — a telemetry outage must not fail the agent
    run or the job.
    """

    def on_llm_call(metrics: dict) -> None:
        llm_calls.append(metrics)
        if session_factory is None:
            return
        try:
            with session_factory() as telemetry_session:
                provider_health.record(telemetry_session, metrics)
                circuit_breaker.record_outcome(
                    telemetry_session, metrics.get("provider"),
                    success=metrics.get("success", True),
                    error_code=metrics.get("error_code"),
                )
        except Exception:  # noqa: BLE001 - telemetry must never fail the job
            logger.exception("provider telemetry recording failed", extra={
                "job_id": str(job.id), "provider": metrics.get("provider"),
            })

    return on_llm_call


async def _process_job_async(
    session: Session, job: AgentAnalysisJob, worker_id: str,
    session_factory, heartbeat_interval_s: float,
) -> None:
    llm_calls: list[dict] = []
    on_agent_complete = _make_progress_callback(job, session)
    on_llm_call = _make_llm_call_sink(job, llm_calls, session_factory)

    heartbeat_task = None
    if session_factory is not None:
        heartbeat_task = asyncio.create_task(
            _heartbeat_loop(session_factory, job.id, worker_id, heartbeat_interval_s)
        )

    try:
        result = await analyze_project_with_agents(
            session,
            str(job.project_id),
            user_id=str(job.created_by) if job.created_by else "system",
            job_id=str(job.id),
            on_agent_complete=on_agent_complete,
            on_llm_call=on_llm_call,
        )
    except AIProviderError as exc:
        fail_job(session, job, exc.code, str(exc), llm_calls=llm_calls)
        return
    except RuntimeError as exc:
        # Project Intake's own rejection (e.g. no contract_text) — see
        # app/agents/run.py's docstring; not a provider failure.
        fail_job(session, job, "AGENT_INTAKE_REJECTED", str(exc), llm_calls=llm_calls)
        return
    except Exception as exc:  # noqa: BLE001 - never leave a job stuck PROCESSING
        fail_job(session, job, "AGENT_PIPELINE_ERROR", repr(exc), llm_calls=llm_calls)
        return
    finally:
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

    job.status = AgentJobStatus.completed
    job.result = result
    job.progress_percent = 100
    job.current_agent = None
    job.estimated_remaining_seconds = 0
    job.llm_calls = llm_calls
    job.completed_at = _now()
    session.commit()


def process_job(
    session: Session, job: AgentAnalysisJob, worker_id: str | None = None,
    session_factory=None, heartbeat_interval_s: float = DEFAULT_HEARTBEAT_INTERVAL_S,
) -> None:
    worker_id = worker_id or job.worker_id
    asyncio.run(_process_job_async(session, job, worker_id, session_factory, heartbeat_interval_s))


# --------------------------------------------------------------------------
# Run loop
# --------------------------------------------------------------------------
def run_once(
    session_factory, worker_id: str | None = None,
    stale_after: timedelta = DEFAULT_HEARTBEAT_STALE_AFTER,
    heartbeat_interval_s: float = DEFAULT_HEARTBEAT_INTERVAL_S,
) -> bool:
    """Process at most one job (after reclaiming any stale ones). Returns
    True if a job was handled."""
    worker_id = worker_id or generate_worker_id()
    with session_factory() as session:
        reclaim_stale_jobs(session, stale_after)
        job = claim_one(session, worker_id)
        if job is None:
            return False
        process_job(session, job, worker_id, session_factory=session_factory,
                    heartbeat_interval_s=heartbeat_interval_s)
        return True


def run_forever(
    session_factory,
    idle_sleep: float = 2.0,
    sleep=time.sleep,
    stale_after: timedelta = DEFAULT_HEARTBEAT_STALE_AFTER,
    heartbeat_interval_s: float = DEFAULT_HEARTBEAT_INTERVAL_S,
) -> None:
    worker_id = generate_worker_id()  # one stable identity for this process's whole lifetime
    while True:
        if not run_once(session_factory, worker_id=worker_id, stale_after=stale_after,
                        heartbeat_interval_s=heartbeat_interval_s):
            sleep(idle_sleep)
