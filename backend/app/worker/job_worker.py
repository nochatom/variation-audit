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

from sqlalchemy import func, select
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.orm import Session

# job_id/project_id/error_code only — never prompt text, document content,
# or credentials (see fail_job below and its module-docstring note).
logger = logging.getLogger("app.worker.job_worker")

from app.engine.client import EngineCancelled, EngineClient, EngineError, EngineTimeout
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
from app.worker.progress import STAGE_PCT, ProgressReporter


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
def build_request(session: Session, job: AnalysisJob, loader: DocumentLoader,
                  reporter: ProgressReporter | None = None) -> AnalysisRequest:
    project = session.get(Project, job.project_id)
    docs = session.execute(
        select(Document).where(Document.project_id == job.project_id)
    ).scalars().all()

    if reporter is not None:
        reporter.total_documents = len(docs)
        reporter.emit("Loading Documents", "running", STAGE_PCT["Queue"] + 3)

    documents: list[DocumentIn] = []
    # Perf instrumentation only (no behaviour change): per-document load
    # timing + a total-loop time, so a slow storage read on one document is
    # visible on its own line instead of hidden inside the job's total time.
    perf_t_loop = time.perf_counter()
    for i, d in enumerate(docs):
        logger.info("perf: START document %s (%d/%d)", d.id, i + 1, len(docs))
        perf_t0 = time.perf_counter()
        # The real work: pull each document's content from object storage.
        content = loader.load(d.storage_key)
        perf_elapsed = time.perf_counter() - perf_t0
        logger.info("perf: doc %s load time: %.3fs", d.id, perf_elapsed)
        documents.append(DocumentIn(
            document_id=str(d.id), type=d.source_type,
            timestamp=d.doc_timestamp, source=d.source, content=content,
        ))
        logger.info("perf: END document %s (%.3fs)", d.id, perf_elapsed)
        if reporter is not None:
            reporter.processed_documents += 1
            reporter.current_document = d.source or str(d.id)
            span = STAGE_PCT["Loading Documents"] - STAGE_PCT["Queue"]
            pct = STAGE_PCT["Queue"] + int(span * reporter.processed_documents / max(1, reporter.total_documents))
            reporter.emit("Loading Documents", "running", pct, current_document=reporter.current_document)

    logger.info("perf: document load loop total (%d docs): %.3fs",
               len(docs), time.perf_counter() - perf_t_loop)

    if reporter is not None:
        reporter.current_document = None
        reporter.emit("Loading Documents", "completed", STAGE_PCT["Loading Documents"])
        # Content is pre-extracted at upload; assembling the request is the
        # product side's "parse/read" step for each source category.
        reporter.emit("Parsing Documents", "completed", STAGE_PCT["Parsing Documents"])
        reporter.emit("Reading Contract", "completed", STAGE_PCT["Reading Contract"])
        reporter.emit("Reading Scope", "completed", STAGE_PCT["Reading Scope"])
        reporter.emit("Reading RFIs", "completed", STAGE_PCT["Reading RFIs"])
        reporter.emit("Reading Emails", "completed", STAGE_PCT["Reading Emails"])

    return AnalysisRequest(
        request_id=job.request_id,
        project_id=str(job.project_id),
        company_id=str(job.company_id),
        contract_text=(project.contract_text if project else None) or "",
        scope_text=(project.scope_text if project else None) or "",
        state=(project.state if project else None),
        documents=documents,
    )


# --------------------------------------------------------------------------
# Result ingestion
# --------------------------------------------------------------------------
def ingest_result(session: Session, job: AnalysisJob, poll: JobPoll,
                  reporter: ProgressReporter | None = None) -> None:
    result: AnalysisResult | None = poll.result
    job.engine_version = poll.engine_version or (result.engine_version if result else None)
    job.engine_job_id = poll.job_id

    if reporter is not None:
        reporter.emit("AI Analysis", "completed", STAGE_PCT["AI Analysis"])

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
            if reporter is not None:
                reporter.variations_found += 1  # real count — one detected variation persisted

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
                if reporter is not None:
                    reporter.evidence_links += 1  # real count — one evidence link persisted

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

        # These stages all happen inside the engine's single call; the worker
        # observes them only through the persisted result, so it reports them
        # completed with the REAL counts it just ingested (never mid-stage
        # fabrication).
        if reporter is not None:
            reporter.emit("Variation Detection", "completed", STAGE_PCT["Variation Detection"])
            reporter.emit("Evidence Linking", "completed", STAGE_PCT["Evidence Linking"])
            reporter.emit("Cost & Time Estimation", "completed", STAGE_PCT["Cost & Time Estimation"])
            reporter.emit("Confidence Scoring", "completed", STAGE_PCT["Confidence Scoring"])

        # Job-level rollups from the contract v1.2 baseline + totals.
        if result.baseline is not None:
            job.baseline = result.baseline.model_dump()
        job.recoverable_total = result.recoverable_total
        job.time_bar_at_risk = result.time_bar_at_risk

        if reporter is not None:
            reporter.emit("Building Report", "completed", STAGE_PCT["Building Report"])

    job.status = JobStatus.succeeded
    job.finished_at = _now()
    _notify(session, job, "analysis_complete")
    session.commit()
    logger.info("job.succeeded", extra={"job_id": str(job.id), "project_id": str(job.project_id)})
    if reporter is not None:
        reporter.emit("Finalizing", "completed", STAGE_PCT["Finalizing"])
        reporter.emit("Completed", "completed", 100)


def fail_job(session: Session, job: AnalysisJob, code: str, message: str, retryable: bool) -> None:
    job.status = JobStatus.failed
    job.error_code = code
    job.error_message = message[:2000]
    job.error_retryable = retryable
    job.finished_at = _now()
    _notify(session, job, "analysis_failed", {"code": code, "retryable": retryable})
    try:
        session.commit()
    except StaleDataError:
        # The job row was deleted under us (e.g. its project was removed while
        # the engine was still running). There is nothing left to fail — roll
        # back and return rather than letting the exception bubble up and take
        # the whole worker loop down with it (a dead worker leaves every later
        # job stuck "queued"). run_forever also guards this, but handling it
        # here keeps the job's own failure path clean.
        session.rollback()
        logger.warning("job.fail_row_vanished", extra={"job_id": str(job.id)})
        return
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


def cancel_job(session: Session, job: AnalysisJob) -> None:
    """Terminalize a job the user cancelled mid-run. This is NOT a failure —
    it's an explicit, expected user action, so it gets its own status."""
    job.status = JobStatus.cancelled
    job.finished_at = _now()
    _notify(session, job, "analysis_cancelled")
    try:
        session.commit()
    except StaleDataError:
        session.rollback()
        logger.warning("job.cancel_row_vanished", extra={"job_id": str(job.id)})
        return
    logger.info("job.cancelled", extra={"job_id": str(job.id), "project_id": str(job.project_id)})


# --------------------------------------------------------------------------
# Processing one job
# --------------------------------------------------------------------------
def process_job(session: Session, client: EngineClient, job: AnalysisJob, loader: DocumentLoader,
                reporter: ProgressReporter | None = None, session_factory=None) -> None:
    # Cooperative cancellation: read the job's cancel signal in a fresh, short
    # session each poll (the request is set by the cancel endpoint in another
    # process). A read hiccup must never fail the job, so it's swallowed.
    def _is_cancel_requested() -> bool:
        if session_factory is None:
            return False
        try:
            with session_factory() as s:
                return s.execute(
                    select(AnalysisJob.cancel_requested_at).where(AnalysisJob.id == job.id)
                ).scalar_one_or_none() is not None
        except Exception:  # noqa: BLE001
            return False

    try:
        if _is_cancel_requested():
            raise EngineCancelled()
        request = build_request(session, job, loader, reporter)
        if reporter is not None:
            reporter.emit("AI Analysis", "running", STAGE_PCT["AI Analysis"] - 8)
        # AI Analysis is a single long engine call (can run for minutes) with no
        # sub-events. Emit a heartbeat on every poll so the live stream keeps
        # ticking (updating elapsed) and the client never falsely reports a
        # stall while the engine is genuinely working.
        def _heartbeat() -> None:
            if reporter is not None:
                reporter.emit("AI Analysis", "running", STAGE_PCT["AI Analysis"] - 8)
        poll = client.run_to_completion(request, on_poll=_heartbeat, cancel_check=_is_cancel_requested)
    except EngineCancelled:
        if reporter is not None:
            reporter.cancelled()
        cancel_job(session, job)
        return
    except EngineTimeout as exc:
        if reporter is not None:
            reporter.fail()
        fail_job(session, job, exc.code, str(exc), exc.retryable)
        return
    except EngineError as exc:
        if reporter is not None:
            reporter.fail()
        fail_job(session, job, exc.code, str(exc), exc.retryable)
        return
    except Exception as exc:  # noqa: BLE001 - never leave a job stuck "running"
        # Unlike EngineTimeout/EngineError (expected, already-classified
        # failures), this is genuinely unexpected — log the full traceback
        # server-side (job_id/project_id context only) so it's investigable;
        # fail_job's own "job.failed" line still records the classification.
        if reporter is not None:
            reporter.fail()
        logger.exception("job.unexpected_error", extra={
            "job_id": str(job.id), "project_id": str(job.project_id),
        })
        fail_job(session, job, "INTERNAL", repr(exc), retryable=True)
        return

    if poll.status == JobStatus.failed:
        err = poll.error
        if reporter is not None:
            reporter.fail()
        fail_job(
            session, job,
            err.code if err else "INTERNAL",
            err.message if err else "engine reported failure",
            bool(err.retryable) if err else True,
        )
    else:
        ingest_result(session, job, poll, reporter)


# --------------------------------------------------------------------------
# Run loop
# --------------------------------------------------------------------------
def run_once(session_factory, client: EngineClient, loader: DocumentLoader) -> bool:
    """Process at most one job. Returns True if a job was handled."""
    with session_factory() as session:
        job = claim_one(session)
        if job is None:
            return False
        # Real progress reporting: the reporter writes append-only events in
        # its own short-lived sessions (see progress.ProgressReporter) so they
        # stream to the SSE endpoint live and can never fail the job. The doc
        # count is the real number of documents on the project.
        total_docs = session.execute(
            select(func.count()).select_from(Document).where(Document.project_id == job.project_id)
        ).scalar_one()
        reporter = ProgressReporter(session_factory, job, total_documents=total_docs)
        # The claim itself (status queued -> running) is the completed "Queue" step.
        reporter.emit("Queue", "completed", STAGE_PCT["Queue"])
        process_job(session, client, job, loader, reporter, session_factory=session_factory)
        return True


def run_forever(session_factory, client: EngineClient, loader: DocumentLoader,
                idle_sleep: float = 2.0, sleep=time.sleep) -> None:
    while True:
        try:
            handled = run_once(session_factory, client, loader)
        except Exception:  # noqa: BLE001
            # A single poisoned job/iteration (an unexpected DB error, a
            # vanished row, an engine-client surprise) must NEVER kill the
            # worker — a dead worker silently leaves every later job stuck
            # "queued" with no way to recover. Log with traceback and keep the
            # loop alive; back off like an idle tick so we don't hot-spin.
            logger.exception("worker.iteration_failed")
            handled = False
        if not handled:
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
