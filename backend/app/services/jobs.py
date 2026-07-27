"""Analysis job service — idempotent enqueue (decision .21.4).

The product API calls `enqueue_analysis` when a user triggers analysis. The
worker (app/worker/job_worker.py) later claims and runs the queued job.

Idempotency: a `request_id` seen within the dedup window returns the existing
job instead of creating a duplicate (prevents double-charged engine runs). A
request_id reused with a *different* project raises IdempotencyConflict (409).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AnalysisJob, AnalysisUsageEvent, JobStatus


class IdempotencyConflict(Exception):
    """Same request_id submitted with a different payload (contract -> 409)."""


def enqueue_analysis(
    session: Session,
    *,
    company_id: uuid.UUID,
    project_id: uuid.UUID,
    created_by: uuid.UUID | None = None,
    request_id: uuid.UUID | None = None,
) -> AnalysisJob:
    """Create a queued analysis job, idempotent on request_id."""
    if request_id is None:
        request_id = uuid.uuid4()

    existing = session.execute(
        select(AnalysisJob).where(AnalysisJob.request_id == request_id)
    ).scalar_one_or_none()

    if existing is not None:
        if existing.project_id != project_id or existing.company_id != company_id:
            raise IdempotencyConflict(
                f"request_id {request_id} already used for a different project"
            )
        window = timedelta(days=get_settings().idempotency_window_days)
        if _aware(existing.created_at) >= datetime.now(timezone.utc) - window:
            return existing  # idempotent replay within window
        # Outside the window the unique constraint still holds; reuse the row.
        return existing

    job = AnalysisJob(
        company_id=company_id,
        project_id=project_id,
        created_by=created_by,
        request_id=request_id,
        status=JobStatus.queued,
    )
    session.add(job)
    session.flush()  # assigns job.id for the usage-event FK below
    # Consumes one unit of the org's monthly analysis quota. Written in the
    # same commit as the job row so "job created" and "quota consumed" can
    # never disagree; deliberately a row in the immutable
    # analysis_usage_events ledger, not a re-count of analysis_jobs — see
    # AnalysisUsageEvent's docstring for why (project-delete cascade would
    # otherwise silently refund usage). The caller (routers/projects.py)
    # holds the org's Subscription row lock (billing_service.
    # enforce_analysis_limit) across this same session/transaction, so this
    # insert is what a concurrent request's blocked quota check sees once it
    # proceeds.
    session.add(AnalysisUsageEvent(company_id=company_id, project_id=project_id, job_id=job.id))
    session.commit()
    session.refresh(job)
    return job


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
