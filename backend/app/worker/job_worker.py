"""Analysis job worker.

Runs as its own process (architecture decision: separate worker, same image).
Loop: claim one queued job via `FOR UPDATE SKIP LOCKED`, drive the stateless
engine through the v1.1 contract, ingest results into the product DB, notify.

A job is the engine's client; the product owns all persistence.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

# job_id/project_id/error_code only — never prompt text, document content,
# or credentials (see fail_job below and its module-docstring note).
logger = logging.getLogger("app.worker.job_worker")

from app.engine.client import EngineClient, EngineError, EngineTimeout
from app.engine.schemas import AnalysisRequest, AnalysisResult, DocumentIn, JobPoll
from app.models import (
    AnalysisJob,
    BasisQuality,
    ConfidenceBand,
    Document,
    Evidence,
    JobStatus,
    Notification,
    Project,
    ValueEstimate,
    Variation,
)


# --------------------------------------------------------------------------
# Confidence band mapping — single source of truth (decision .21.3)
#   low: 0.00-0.49 | medium: 0.50-0.79 | high: 0.80-1.00
# --------------------------------------------------------------------------
def band_for_score(score: float | Decimal | None) -> ConfidenceBand | None:
    if score is None:
        return None
    s = float(score)
    if s < 0.5:
        return ConfidenceBand.low
    if s < 0.8:
        return ConfidenceBand.medium
    return ConfidenceBand.high


class DocumentLoader(Protocol):
    """Loads raw document content from object storage (S3 ap-southeast-2)."""

    def load(self, storage_key: str) -> str: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Claiming
# --------------------------------------------------------------------------
def claim_one(session: Session) -> AnalysisJob | None:
    """Atomically claim the oldest queued job. Concurrency-safe across workers."""
    job = session.execute(
        select(AnalysisJob)
        .where(AnalysisJob.status == JobStatus.queued)
        .order_by(AnalysisJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if job is None:
        return None
    job.status = JobStatus.running
    job.started_at = _now()
    session.commit()
    logger.info("job.claimed", extra={"job_id": str(job.id), "project_id": str(job.project_id)})
    return job


# --------------------------------------------------------------------------
# Request building
# --------------------------------------------------------------------------
def build_request(session: Session, job: AnalysisJob, loader: DocumentLoader) -> AnalysisRequest:
    project = session.get(Project, job.project_id)
    docs = session.execute(
        select(Document).where(Document.project_id == job.project_id)
    ).scalars().all()
    return AnalysisRequest(
        request_id=job.request_id,
        project_id=str(job.project_id),
        company_id=str(job.company_id),
        contract_text=(project.contract_text if project else None) or "",
        scope_text=(project.scope_text if project else None) or "",
        state=(project.state if project else None),
        documents=[
            DocumentIn(
                document_id=str(d.id),
                type=d.source_type,
                timestamp=d.doc_timestamp,
                source=d.source,
                content=loader.load(d.storage_key),
            )
            for d in docs
        ],
    )


# --------------------------------------------------------------------------
# Result ingestion
# --------------------------------------------------------------------------
def ingest_result(session: Session, job: AnalysisJob, poll: JobPoll) -> None:
    result: AnalysisResult | None = poll.result
    job.engine_version = poll.engine_version or (result.engine_version if result else None)
    job.engine_job_id = poll.job_id

    if result is None and poll.result_url:
        # >1MB result delivered out-of-band; record the ref for later fetch.
        job.result_ref = poll.result_url
    elif result is not None:
        for v in result.variations:
            band = v.confidence_band or band_for_score(v.confidence_score)
            variation = Variation(
                id=uuid.UUID(v.variation_id) if _is_uuid(v.variation_id) else uuid.uuid4(),
                company_id=job.company_id,
                project_id=job.project_id,
                job_id=job.id,
                title=v.title,
                description=v.description,
                engine_status=v.status,
                confidence_score=Decimal(str(v.confidence_score)),
                confidence_band=band,
                confidence_factors=v.confidence_factors or None,
                time_bar_risk=bool(v.time_bar_risk),
            )
            session.add(variation)
            session.flush()  # assign variation.id for FKs

            for e in v.evidence:
                session.add(
                    Evidence(
                        variation_id=variation.id,
                        source_type=e.type,
                        source_document_id=(
                            uuid.UUID(e.source_document_id)
                            if e.source_document_id and _is_uuid(e.source_document_id)
                            else None
                        ),
                        reference=e.reference,
                        quote=e.quote,
                    )
                )

            if v.estimated_value is not None:
                ev = v.estimated_value
                session.add(
                    ValueEstimate(
                        variation_id=variation.id,
                        amount=ev.amount,
                        estimate_low=ev.estimate_low,
                        estimate_high=ev.estimate_high,
                        currency=ev.currency or "AUD",
                        basis_quality=ev.basis_quality or BasisQuality.none,
                        valuation_confidence_score=ev.valuation_confidence_score,
                        confidence=ev.confidence or band_for_score(ev.valuation_confidence_score)
                        or ConfidenceBand.low,
                    )
                )

        # Job-level rollups from the contract v1.2 baseline + totals.
        if result.baseline is not None:
            job.baseline = result.baseline.model_dump()
        job.recoverable_total = result.recoverable_total
        job.time_bar_at_risk = result.time_bar_at_risk

    job.status = JobStatus.succeeded
    job.finished_at = _now()
    _notify(session, job, "analysis_complete")
    session.commit()
    logger.info("job.succeeded", extra={"job_id": str(job.id), "project_id": str(job.project_id)})


def fail_job(session: Session, job: AnalysisJob, code: str, message: str, retryable: bool) -> None:
    job.status = JobStatus.failed
    job.error_code = code
    job.error_message = message[:2000]
    job.error_retryable = retryable
    job.finished_at = _now()
    _notify(session, job, "analysis_failed", {"code": code, "retryable": retryable})
    session.commit()
    # Every failure path (EngineTimeout, EngineError, an unexpected
    # exception, or the engine reporting failure) funnels through here, so
    # this is the single place job failures become visible in logs — job_id/
    # project_id/error_code only, never the message itself (which may be an
    # engine/library exception's text — the DB row is the place to look up
    # full detail, not the log stream).
    logger.warning("job.failed", extra={
        "job_id": str(job.id), "project_id": str(job.project_id),
        "error_code": code, "retryable": retryable,
    })


# --------------------------------------------------------------------------
# Processing one job
# --------------------------------------------------------------------------
def process_job(session: Session, client: EngineClient, job: AnalysisJob, loader: DocumentLoader) -> None:
    try:
        request = build_request(session, job, loader)
        poll = client.run_to_completion(request)
    except EngineTimeout as exc:
        fail_job(session, job, exc.code, str(exc), exc.retryable)
        return
    except EngineError as exc:
        fail_job(session, job, exc.code, str(exc), exc.retryable)
        return
    except Exception as exc:  # noqa: BLE001 - never leave a job stuck "running"
        # Unlike EngineTimeout/EngineError (expected, already-classified
        # failures), this is genuinely unexpected — log the full traceback
        # server-side (job_id/project_id context only) so it's investigable;
        # fail_job's own "job.failed" line still records the classification.
        logger.exception("job.unexpected_error", extra={
            "job_id": str(job.id), "project_id": str(job.project_id),
        })
        fail_job(session, job, "INTERNAL", repr(exc), retryable=True)
        return

    if poll.status == JobStatus.failed:
        err = poll.error
        fail_job(
            session, job,
            err.code if err else "INTERNAL",
            err.message if err else "engine reported failure",
            bool(err.retryable) if err else True,
        )
    else:
        ingest_result(session, job, poll)


# --------------------------------------------------------------------------
# Run loop
# --------------------------------------------------------------------------
def run_once(session_factory, client: EngineClient, loader: DocumentLoader) -> bool:
    """Process at most one job. Returns True if a job was handled."""
    with session_factory() as session:
        job = claim_one(session)
        if job is None:
            return False
        process_job(session, client, job, loader)
        return True


def run_forever(session_factory, client: EngineClient, loader: DocumentLoader,
                idle_sleep: float = 2.0, sleep=time.sleep) -> None:
    while True:
        if not run_once(session_factory, client, loader):
            sleep(idle_sleep)


# --------------------------------------------------------------------------
def _notify(session: Session, job: AnalysisJob, type_: str, extra: dict | None = None) -> None:
    user_id = job.created_by
    if user_id is None:
        return  # no triggering user to notify
    payload = {"job_id": str(job.id), "project_id": str(job.project_id)}
    if extra:
        payload.update(extra)
    session.add(Notification(company_id=job.company_id, user_id=user_id,
                             type=type_, payload=payload))


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False
