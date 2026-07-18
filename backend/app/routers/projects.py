"""Project endpoints: create/list/get, contract & comms upload, analyze."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import parsing
from app.auth.deps import ensure_member, get_current_user, get_db, require_admin
from app.models import AnalysisJob, JobStatus, Membership, Project, ProjectStatus, SourceType, User
from app.rate_limit import ANALYSIS_LIMIT, UPLOAD_LIMIT, limiter
from app.services import billing as billing_service
from app.services import jobs
from app.services import projects as project_service
from app.storage import build_loader, get_store

router = APIRouter(prefix="/projects", tags=["projects"])
logger = logging.getLogger("va.projects.router")

# Australian states/territories — mirrors the frontend's <select> (defense in
# depth: validated server-side too, since the API is reachable directly).
AU_STATES = {"NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"}
MAX_TEXT_LEN = 500_000        # ~500KB of contract/scope text — generous but bounded
MAX_CONTRACT_BYTES = 20 * 1024 * 1024   # 20MB — contract/scope PDFs
MAX_CSV_BYTES = 10 * 1024 * 1024        # 10MB — register CSV uploads


def _parse_or_400(parse_fn, *args):
    """Malformed uploads (corrupt PDF, broken CSV, wrong file renamed to
    .pdf) must be a clean 400, not an unhandled 500 with a stack trace in
    the logs — the parser libraries raise a wide variety of exception types
    on hostile input, so this deliberately catches broadly."""
    try:
        return parse_fn(*args)
    except Exception:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "could not parse the uploaded file — check it is a valid, uncorrupted file")


# Content types browsers legitimately send for the contract upload. A .pdf
# filename with a non-PDF content type is rejected before parsing.
_PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf", "application/octet-stream"}


async def _read_capped(file: UploadFile, max_bytes: int) -> bytes:
    """Read an upload, rejecting it (413) if it exceeds max_bytes.

    Reads in chunks rather than the whole body up front, so an oversized
    upload is rejected without buffering the entire payload into memory.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"file exceeds the {max_bytes // (1024 * 1024)}MB limit",
            )
        chunks.append(chunk)
    return b"".join(chunks)


# ---- schemas -------------------------------------------------------------
class CreateProjectRequest(BaseModel):
    company_id: uuid.UUID
    name: str = Field(min_length=1, max_length=300)
    contract_text: str | None = Field(default=None, max_length=MAX_TEXT_LEN)
    scope_text: str | None = Field(default=None, max_length=MAX_TEXT_LEN)
    state: str | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be blank")
        return v

    @field_validator("state")
    @classmethod
    def _valid_au_state(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        v = v.strip().upper()
        if v not in AU_STATES:
            raise ValueError(f"state must be one of {sorted(AU_STATES)}")
        return v


class ProjectOut(BaseModel):
    id: str
    company_id: str
    name: str
    state: str | None = None
    status: str
    has_contract: bool = False
    archived_at: str | None = None


def _out(p) -> ProjectOut:
    return ProjectOut(id=str(p.id), company_id=str(p.company_id), name=p.name,
                      state=p.state, status=p.status.value,
                      has_contract=bool(p.contract_text),
                      archived_at=p.archived_at.isoformat() if p.archived_at else None)


# ---- endpoints -----------------------------------------------------------
@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(req: CreateProjectRequest, user: User = Depends(get_current_user),
                   session: Session = Depends(get_db)) -> ProjectOut:
    ensure_member(session, user, req.company_id)
    try:
        billing_service.enforce_project_limit(session, req.company_id)
    except billing_service.PlanLimitExceeded as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                            {"error_code": exc.code, "message": str(exc)})
    project = project_service.create_project(
        session, company_id=req.company_id, created_by=user.id, name=req.name,
        contract_text=req.contract_text, scope_text=req.scope_text, state=req.state,
        status=ProjectStatus.in_progress,
    )
    return _out(project)


@router.get("", response_model=list[ProjectOut])
def list_projects(company_id: uuid.UUID, archived: bool = False,
                  user: User = Depends(get_current_user),
                  session: Session = Depends(get_db)) -> list[ProjectOut]:
    """Active projects by default; ?archived=true lists archived ones instead."""
    ensure_member(session, user, company_id)
    return [_out(p) for p in
            project_service.list_projects(session, company_id, archived=archived)]


def _check_upload_limits(session: Session, company_id: uuid.UUID, rows: list[dict]) -> None:
    """Server-side plan-limit enforcement (.24) for a batch of parsed rows
    about to become Document rows — document count and storage size."""
    total_bytes = sum(len(r["text"].encode("utf-8")) for r in rows)
    try:
        billing_service.enforce_document_limit(session, company_id, additional=len(rows))
        billing_service.enforce_storage_limit(session, company_id, additional_bytes=total_bytes)
    except billing_service.PlanLimitExceeded as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                            {"error_code": exc.code, "message": str(exc)})


def _load_project(session, user, project_id):
    """Resolve an org-scoped project for the caller (404 if not visible)."""
    company_ids = [
        m.company_id for m in session.execute(
            select(Membership).where(Membership.user_id == user.id)
        ).scalars().all()
    ]
    project = session.get(Project, project_id)
    if project is None or project.company_id not in company_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID, user: User = Depends(get_current_user),
                session: Session = Depends(get_db)) -> ProjectOut:
    return _out(_load_project(session, user, project_id))


# ---- lifecycle: archive (any member, reversible) / delete (admin, permanent) ----
@router.post("/{project_id}/archive", response_model=ProjectOut)
def archive_project(project_id: uuid.UUID, user: User = Depends(get_current_user),
                    session: Session = Depends(get_db)) -> ProjectOut:
    """Hide the project from the default dashboard. Reversible via /unarchive."""
    project = _load_project(session, user, project_id)
    return _out(project_service.archive_project(session, project, actor=user))


@router.post("/{project_id}/unarchive", response_model=ProjectOut)
def unarchive_project(project_id: uuid.UUID, user: User = Depends(get_current_user),
                      session: Session = Depends(get_db)) -> ProjectOut:
    """Restore an archived project to the active dashboard."""
    project = _load_project(session, user, project_id)
    return _out(project_service.unarchive_project(session, project, actor=user))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: uuid.UUID, user: User = Depends(get_current_user),
                   session: Session = Depends(get_db),
                   store=Depends(get_store)) -> None:
    """PERMANENTLY delete a project and all its documents, jobs, variations,
    evidence, estimates and comments (DB-level cascades + best-effort object
    storage cleanup). Admin-only; irreversible — the UI requires typing the
    project name to confirm.

    Archive-first is enforced here, not just hidden in the UI: an active
    project must be archived before it can be permanently deleted (409 if
    not). This is a deliberate safety gate against accidental data loss,
    not something a direct API call should be able to skip."""
    project = _load_project(session, user, project_id)
    require_admin(session, user, project.company_id)
    if project.archived_at is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "project must be archived before it can be permanently deleted",
        )
    project_service.delete_project(session, project, actor=user, store=store)


@router.post("/{project_id}/contract", response_model=ProjectOut)
@limiter.limit(UPLOAD_LIMIT)
async def upload_contract(request: Request, response: Response,
                          project_id: uuid.UUID, is_scope: bool = False,
                          file: UploadFile = File(...),
                          user: User = Depends(get_current_user),
                          session: Session = Depends(get_db)) -> ProjectOut:
    project = _load_project(session, user, project_id)
    is_pdf = (file.filename or "").lower().endswith(".pdf")
    if is_pdf and file.content_type and file.content_type not in _PDF_CONTENT_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "file has a .pdf name but a non-PDF content type")
    data = await _read_capped(file, MAX_CONTRACT_BYTES)
    # Magic-byte validation — content type and filename are both
    # caller-controlled, so neither is trusted on its own: a PDF must
    # actually start with the %PDF- header. (No stream-reset needed: the
    # capped read above buffered the full body, and `data` is what gets
    # parsed.) The pypdf parse inside extract_text then validates real
    # structure; _parse_or_400 turns any parser failure into a clean 400.
    if is_pdf and not data.startswith(b"%PDF-"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "file is not a valid PDF (missing PDF header)")
    text = _parse_or_400(parsing.extract_text, file.filename or "", data)
    # Bound the EXTRACTED text too, not just the raw upload — the JSON create
    # path caps contract_text at MAX_TEXT_LEN, and this path must not be a
    # way around that cap (or around the plan storage quota).
    if len(text) > MAX_TEXT_LEN:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE,
                            f"extracted text exceeds the {MAX_TEXT_LEN // 1000}KB limit")
    # This upload REPLACES the project's existing contract/scope text (already
    # counted in current usage), so the added storage is only the delta — the
    # new text's byte size minus what's being overwritten. Without this a
    # same-size re-upload would be double-counted and wrongly rejected.
    old_bytes = len(((project.scope_text if is_scope else project.contract_text) or "").encode("utf-8"))
    delta = max(0, len(text.encode("utf-8")) - old_bytes)
    try:
        billing_service.enforce_storage_limit(session, project.company_id, additional_bytes=delta)
    except billing_service.PlanLimitExceeded as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                            {"error_code": exc.code, "message": str(exc)})
    if is_scope:
        project_service.set_contract(session, project, scope_text=text)
    else:
        project_service.set_contract(session, project, contract_text=text)
    return _out(project)


class DocumentUploadResponse(BaseModel):
    id: str
    project_id: str
    source_type: str
    storage_key: str
    size_bytes: int


@router.post("/{project_id}/documents", response_model=DocumentUploadResponse,
             status_code=status.HTTP_201_CREATED)
@limiter.limit(UPLOAD_LIMIT)
async def upload_document(request: Request, response: Response,
                          project_id: uuid.UUID, file: UploadFile = File(...),
                          user: User = Depends(get_current_user),
                          session: Session = Depends(get_db),
                          store=Depends(get_store)) -> DocumentUploadResponse:
    """Upload a single arbitrary supporting document (PDF or text) — stored
    in object storage (Supabase Storage's private `project-documents`
    bucket in production, via app.storage.build_loader()) and registered as
    a Document row (source_type=document — the one SourceType value with no
    other upload path). Distinct from /comms, /rfis, /site-instructions,
    /meeting-minutes, which each ingest a structured CSV register of many
    rows in one call; this is for a single standalone file.

    Reuses the exact same validation, parsing, and persistence pattern as
    /contract (magic-byte PDF check, extract_text, MAX_TEXT_LEN cap) and
    project_service.add_document() (the same function every CSV-register
    endpoint already uses) — no new service-layer logic.
    """
    project = _load_project(session, user, project_id)

    filename = file.filename or ""
    is_pdf = filename.lower().endswith(".pdf")
    if is_pdf and file.content_type and file.content_type not in _PDF_CONTENT_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "file has a .pdf name but a non-PDF content type")

    data = await _read_capped(file, MAX_CONTRACT_BYTES)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "uploaded file is empty")
    # Magic-byte validation — same rationale as /contract: filename and
    # content-type are both caller-controlled, neither is trusted alone.
    if is_pdf and not data.startswith(b"%PDF-"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "file is not a valid PDF (missing PDF header)")

    text = _parse_or_400(parsing.extract_text, filename, data)
    if len(text) > MAX_TEXT_LEN:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE,
                            f"extracted text exceeds the {MAX_TEXT_LEN // 1000}KB limit")

    try:
        billing_service.enforce_document_limit(session, project.company_id, additional=1)
        billing_service.enforce_storage_limit(session, project.company_id,
                                              additional_bytes=len(text.encode("utf-8")))
    except billing_service.PlanLimitExceeded as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                            {"error_code": exc.code, "message": str(exc)})

    try:
        document = project_service.add_document(
            session, store, company_id=project.company_id, project_id=project.id,
            source_type=SourceType.document, content=text, source=filename or None,
        )
    except Exception:
        # Object storage (Supabase Storage / S3) is an external dependency —
        # a transient failure there must be a clean 502, not an unhandled
        # 500 with a stack trace, and must be logged with enough context to
        # investigate without ever logging the file's content.
        logger.exception(
            "document upload to object storage failed",
            extra={"project_id": str(project.id), "company_id": str(project.company_id),
                  "uploaded_filename": filename},
        )
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, {
            "error_code": "DOCUMENT_UPLOAD_FAILED",
            "message": "Unable to process this document. Please try again.",
        })

    return DocumentUploadResponse(
        id=str(document.id), project_id=str(project.id),
        source_type=document.source_type.value, storage_key=document.storage_key,
        size_bytes=document.size_bytes or 0,
    )


class CommsUploadResponse(BaseModel):
    project_id: str
    documents_added: int


@router.post("/{project_id}/comms", response_model=CommsUploadResponse)
@limiter.limit(UPLOAD_LIMIT)
async def upload_comms(request: Request, response: Response,
                       project_id: uuid.UUID, file: UploadFile = File(...),
                       user: User = Depends(get_current_user),
                       session: Session = Depends(get_db)) -> CommsUploadResponse:
    project = _load_project(session, user, project_id)
    rows = _parse_or_400(parsing.parse_comms_csv, await _read_capped(file, MAX_CSV_BYTES))
    _check_upload_limits(session, project.company_id, rows)
    store = build_loader()
    for r in rows:
        project_service.add_document(
            session, store, company_id=project.company_id, project_id=project.id,
            source_type=parsing.kind_to_source_type(r.get("kind")),
            content=r["text"], source=r.get("author"), occurred_at=r.get("occurred_at"),
        )
    return CommsUploadResponse(project_id=str(project.id), documents_added=len(rows))


class RfiUploadResponse(BaseModel):
    project_id: str
    documents_added: int


@router.post("/{project_id}/rfis", response_model=RfiUploadResponse)
@limiter.limit(UPLOAD_LIMIT)
async def upload_rfis(request: Request, response: Response,
                      project_id: uuid.UUID, file: UploadFile = File(...),
                      user: User = Depends(get_current_user),
                      session: Session = Depends(get_db),
                      store=Depends(get_store)) -> RfiUploadResponse:
    """Ingest an RFI register CSV — one source_type=rfi Document per RFI row."""
    project = _load_project(session, user, project_id)
    rows = _parse_or_400(parsing.parse_rfi_csv, await _read_capped(file, MAX_CSV_BYTES))
    _check_upload_limits(session, project.company_id, rows)
    for r in rows:
        project_service.add_document(
            session, store, company_id=project.company_id, project_id=project.id,
            source_type=SourceType.rfi, content=r["text"],
            source=r["ref"], occurred_at=r.get("occurred_at"),
        )
    return RfiUploadResponse(project_id=str(project.id), documents_added=len(rows))


class SiteInstructionUploadResponse(BaseModel):
    project_id: str
    documents_added: int


@router.post("/{project_id}/site-instructions", response_model=SiteInstructionUploadResponse)
@limiter.limit(UPLOAD_LIMIT)
async def upload_site_instructions(request: Request, response: Response,
                                   project_id: uuid.UUID,
                                   file: UploadFile = File(...),
                                   user: User = Depends(get_current_user),
                                   session: Session = Depends(get_db),
                                   store=Depends(get_store)) -> SiteInstructionUploadResponse:
    """Ingest a site-instruction register CSV — one source_type=site_instruction Document per row."""
    project = _load_project(session, user, project_id)
    rows = _parse_or_400(parsing.parse_site_instructions_csv, await _read_capped(file, MAX_CSV_BYTES))
    _check_upload_limits(session, project.company_id, rows)
    for r in rows:
        project_service.add_document(
            session, store, company_id=project.company_id, project_id=project.id,
            source_type=SourceType.site_instruction, content=r["text"],
            source=r["ref"], occurred_at=r.get("occurred_at"),
        )
    return SiteInstructionUploadResponse(project_id=str(project.id), documents_added=len(rows))


class MeetingMinutesUploadResponse(BaseModel):
    project_id: str
    documents_added: int


@router.post("/{project_id}/meeting-minutes", response_model=MeetingMinutesUploadResponse)
@limiter.limit(UPLOAD_LIMIT)
async def upload_meeting_minutes(request: Request, response: Response,
                                 project_id: uuid.UUID,
                                 file: UploadFile = File(...),
                                 user: User = Depends(get_current_user),
                                 session: Session = Depends(get_db),
                                 store=Depends(get_store)) -> MeetingMinutesUploadResponse:
    """Ingest a meeting-minutes register CSV — one source_type=meeting_note Document per item."""
    project = _load_project(session, user, project_id)
    rows = _parse_or_400(parsing.parse_meeting_minutes_csv, await _read_capped(file, MAX_CSV_BYTES))
    _check_upload_limits(session, project.company_id, rows)
    for r in rows:
        project_service.add_document(
            session, store, company_id=project.company_id, project_id=project.id,
            source_type=SourceType.meeting_note, content=r["text"],
            source=r["ref"], occurred_at=r.get("occurred_at"),
        )
    return MeetingMinutesUploadResponse(project_id=str(project.id), documents_added=len(rows))


class AnalyzeResponse(BaseModel):
    job_id: str
    status: str


@router.post("/{project_id}/analyze", response_model=AnalyzeResponse,
             status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(ANALYSIS_LIMIT)
def analyze(request: Request, response: Response, project_id: uuid.UUID,
            user: User = Depends(get_current_user),
            session: Session = Depends(get_db)) -> AnalyzeResponse:
    project = _load_project(session, user, project_id)

    # One active analysis per project. If a job is already queued or running,
    # return it (200) instead of enqueuing a duplicate — repeated "Run
    # analysis" clicks would otherwise pile up a backlog the single worker
    # can't drain, and the client would watch a queued job that never starts.
    existing = session.execute(
        select(AnalysisJob)
        .where(AnalysisJob.project_id == project.id,
               AnalysisJob.status.in_((JobStatus.queued, JobStatus.running)))
        .order_by(AnalysisJob.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return AnalyzeResponse(job_id=str(existing.id), status=existing.status.value)

    if not (project.contract_text or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "project has no contract_text; upload a contract before analyzing")
    try:
        billing_service.enforce_analysis_limit(session, project.company_id)
    except billing_service.PlanLimitExceeded as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                            {"error_code": exc.code, "message": str(exc)})
    job = jobs.enqueue_analysis(
        session, company_id=project.company_id, project_id=project.id, created_by=user.id,
    )
    return AnalyzeResponse(job_id=str(job.id), status=job.status.value)


@router.post("/{project_id}/analysis/{job_id}/cancel", response_model=AnalyzeResponse)
def cancel_analysis(project_id: uuid.UUID, job_id: uuid.UUID,
                    user: User = Depends(get_current_user),
                    session: Session = Depends(get_db)) -> AnalyzeResponse:
    """Stop a queued or running analysis.

    - queued: not yet claimed by a worker, so it's cancelled immediately.
    - running: set the cancel signal; the worker observes it between engine
      polls (see job_worker.process_job) and transitions the job to
      "cancelled", stopping its wait on the engine and releasing that slot.
    - already terminal (succeeded/failed/cancelled): idempotent no-op — return
      the current status so a double-click is harmless.
    """
    project = _load_project(session, user, project_id)  # 404 if not the caller's
    job = session.get(AnalysisJob, job_id)
    if job is None or job.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "analysis job not found")

    now = datetime.now(timezone.utc)
    if job.status == JobStatus.queued:
        job.status = JobStatus.cancelled
        job.cancel_requested_at = now
        job.finished_at = now
        session.commit()
        logger.info("analysis.cancelled_queued", extra={"job_id": str(job.id)})
    elif job.status == JobStatus.running:
        job.cancel_requested_at = now  # worker will terminalize it
        session.commit()
        logger.info("analysis.cancel_requested", extra={"job_id": str(job.id)})
    # else: terminal -> no change, idempotent.
    return AnalyzeResponse(job_id=str(job.id), status=job.status.value)
