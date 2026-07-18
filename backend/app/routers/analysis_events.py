"""Server-Sent Events stream of *real* analysis progress.

The worker (app/worker/job_worker.py, via progress.ProgressReporter) appends
one `analysis_job_events` row after every major processing step it genuinely
performs. This endpoint streams those rows to the browser over SSE — it never
synthesises or interpolates progress of its own; it only forwards what the
worker actually wrote.

Contract (each `event: progress` frame's JSON payload) carries exactly the
fields Task 3 requires:
    stage, status, percentage, current_document, processed_documents,
    total_documents, variations_found, evidence_links, elapsed_seconds,
    estimated_remaining
plus `seq` (monotonic ordering) so a reconnecting client can resume with
`Last-Event-ID` and never replay or miss an event.

Additive only: a brand-new GET endpoint. No existing route, model, or worker
behaviour changes, so existing APIs are untouched.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_db
from app.auth.tokens import TokenError, decode_token
from app.db import session_factory
from app.models import AnalysisJob, AnalysisJobEvent, JobStatus, Membership, Project, User

router = APIRouter(prefix="/projects", tags=["analysis-events"])
logger = logging.getLogger("app.routers.analysis_events")

# How often the streamer checks the append-only table for new events, and how
# often it emits a keepalive comment when idle. Small enough to feel live,
# large enough not to hammer Postgres.
_POLL_SECONDS = 1.0
_KEEPALIVE_SECONDS = 15.0
# Hard ceiling so a client that connects to a stuck/orphaned job can never
# hold the streaming task open forever.
_MAX_STREAM_SECONDS = 60 * 30


def _resolve_user(session: Session, token: str | None) -> User:
    """Authenticate an SSE request.

    EventSource cannot set an Authorization header, so the token may arrive as
    a query parameter instead. Either way it's the same signed access token
    the rest of the API uses — decoded and checked identically to
    get_current_user (this endpoint deliberately does NOT weaken auth).
    """
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing access token")
    try:
        payload = decode_token(token)
    except TokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    sub = payload.get("sub")
    user = session.get(User, uuid.UUID(sub)) if sub else None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found or inactive")
    return user


def _authorize(session: Session, user: User, project_id: uuid.UUID, job_id: uuid.UUID) -> None:
    """404 unless the project is visible to the caller AND the job is that
    project's — mirrors projects._load_project's org-isolation semantics so
    this endpoint can't leak a job's existence across orgs."""
    company_ids = [
        m.company_id for m in session.execute(
            select(Membership).where(Membership.user_id == user.id)
        ).scalars().all()
    ]
    project = session.get(Project, project_id)
    if project is None or project.company_id not in company_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    job = session.get(AnalysisJob, job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")


def _serialize(ev: AnalysisJobEvent) -> dict:
    """The exact Task-3 field set, read straight off the persisted row."""
    return {
        "seq": ev.seq,
        "stage": ev.stage,
        "status": ev.status,
        "percentage": ev.percentage,
        "current_document": ev.current_document,
        "processed_documents": ev.processed_documents,
        "total_documents": ev.total_documents,
        "variations_found": ev.variations_found,
        "evidence_links": ev.evidence_links,
        "elapsed_seconds": float(ev.elapsed_seconds) if ev.elapsed_seconds is not None else 0.0,
        "estimated_remaining": (
            float(ev.estimated_remaining) if ev.estimated_remaining is not None else None
        ),
    }


def _fetch_after(job_id: uuid.UUID, last_seq: int) -> list[dict]:
    """Read new events (seq > last_seq) in a fresh short-lived session.

    Runs off the event loop via run_in_threadpool — the sync ORM must never
    block the async streamer. Uses its own session (not the request's), so it
    always sees rows the worker committed in another process/transaction.
    """
    with session_factory() as s:
        rows = s.execute(
            select(AnalysisJobEvent)
            .where(AnalysisJobEvent.job_id == job_id, AnalysisJobEvent.seq > last_seq)
            .order_by(AnalysisJobEvent.seq)
        ).scalars().all()
        return [_serialize(r) for r in rows]


def _job_is_terminal(job_id: uuid.UUID) -> bool:
    """True once the underlying job has reached a terminal state — the stream
    ends shortly after, even if the final progress event was lost (e.g. the
    events table didn't exist, so emit() swallowed the write)."""
    with session_factory() as s:
        job = s.get(AnalysisJob, job_id)
        return job is not None and job.status in (
            JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled,
        )


def _is_terminal_event(payload: dict) -> bool:
    return (
        payload["status"] in ("failed", "cancelled")
        or payload["stage"] == "Completed"
        or payload["percentage"] >= 100
    )


@router.get("/{project_id}/analysis/{job_id}/events")
async def stream_analysis_events(
    project_id: uuid.UUID,
    job_id: uuid.UUID,
    request: Request,
    access_token: str | None = Query(default=None),
    last_event_id: int | None = Query(default=None, alias="lastEventId"),
    session: Session = Depends(get_db),
) -> StreamingResponse:
    """SSE stream of real worker progress events for one analysis job.

    Auth token comes from the `Authorization: Bearer` header when present
    (fetch-based EventSource) or the `access_token` query param (native
    EventSource). Resume with the standard `Last-Event-ID` header or a
    `lastEventId` query param.
    """
    header = request.headers.get("authorization", "")
    bearer = header[7:] if header.lower().startswith("bearer ") else None
    user = _resolve_user(session, bearer or access_token)
    _authorize(session, user, project_id, job_id)

    # Prefer the standard SSE reconnection header; fall back to the query param.
    resume_hdr = request.headers.get("last-event-id")
    try:
        start_seq = int(resume_hdr) if resume_hdr is not None else (last_event_id or 0)
    except ValueError:
        start_seq = 0

    async def event_stream():
        last_seq = start_seq
        elapsed = 0.0
        since_keepalive = 0.0
        # Kick off with a comment so proxies flush headers and the client
        # knows the stream is live even before the first event.
        yield ": connected\n\n"
        while True:
            if await request.is_disconnected():
                return
            try:
                events = await run_in_threadpool(_fetch_after, job_id, last_seq)
            except Exception:  # noqa: BLE001 — a read hiccup must not kill the stream mid-run
                logger.warning("analysis_events.fetch_failed", extra={"job_id": str(job_id)})
                events = []

            if events:
                since_keepalive = 0.0
                for payload in events:
                    last_seq = payload["seq"]
                    yield f"id: {payload['seq']}\nevent: progress\ndata: {json.dumps(payload)}\n\n"
                    if _is_terminal_event(payload):
                        return
            else:
                # No new events: if the job itself is already terminal, the
                # run is over (guards against a lost final event) — otherwise
                # keep the connection warm.
                if await run_in_threadpool(_job_is_terminal, job_id):
                    yield "event: end\ndata: {}\n\n"
                    return
                since_keepalive += _POLL_SECONDS
                if since_keepalive >= _KEEPALIVE_SECONDS:
                    since_keepalive = 0.0
                    yield ": keepalive\n\n"

            await asyncio.sleep(_POLL_SECONDS)
            elapsed += _POLL_SECONDS
            if elapsed >= _MAX_STREAM_SECONDS:
                yield "event: end\ndata: {}\n\n"
                return

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Disable proxy buffering (nginx) so events flush immediately.
            "X-Accel-Buffering": "no",
        },
    )
