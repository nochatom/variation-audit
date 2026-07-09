"""AgentAnalysisJob creation — the "Create Analysis Job -> Queue" half of
the async execution layer. app/agents/worker.py is the consumer.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models import AgentAnalysisJob, AgentJobStatus


def enqueue_agent_analysis(
    session: Session,
    *,
    company_id: uuid.UUID,
    project_id: uuid.UUID,
    created_by: uuid.UUID | None = None,
) -> AgentAnalysisJob:
    """Create a job row and immediately mark it queued.

    No idempotency window here (unlike services/jobs.py's engine-pipeline
    enqueue_analysis) — the agent scaffold has no external per-run billing
    concern yet; every call creates a new job. PENDING is momentary (the row
    is only ever observed at QUEUED or later) but kept as a real status so
    the full PENDING->QUEUED->PROCESSING->COMPLETED/FAILED lifecycle the
    requirement asks for is genuinely modeled, not skipped.
    """
    job = AgentAnalysisJob(
        company_id=company_id,
        project_id=project_id,
        created_by=created_by,
        status=AgentJobStatus.pending,
        progress_percent=0,
    )
    session.add(job)
    session.flush()

    job.status = AgentJobStatus.queued
    session.commit()
    session.refresh(job)
    return job
