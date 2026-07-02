"""Project endpoints: create/list/get, contract & comms upload, analyze."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import parsing
from app.auth.deps import ensure_member, get_current_user, get_db, require_admin
from app.models import Membership, Project, ProjectStatus, SourceType, User
from app.rate_limit import ANALYSIS_LIMIT, UPLOAD_LIMIT, limiter
from app.services import jobs
from app.services import projects as project_service
from app.storage import build_loader, get_store

router = APIRouter(prefix="/projects", tags=["projects"])

# Australian states/territories — mirrors the frontend's <select> (defense in
# depth: validated server-side too, since the API is reachable directly).
AU_STATES = {"NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"}
MAX_TEXT_LEN = 500_000        # ~500KB of contract/scope text — generous but bounded
MAX_CONTRACT_BYTES = 20 * 1024 * 1024   # 20MB — contract/scope PDFs
MAX_CSV_BYTES = 10 * 1024 * 1024        # 10MB — register CSV uploads


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
    project name to confirm."""
    project = _load_project(session, user, project_id)
    require_admin(session, user, project.company_id)
    project_service.delete_project(session, project, actor=user, store=store)


@router.post("/{project_id}/contract", response_model=ProjectOut)
@limiter.limit(UPLOAD_LIMIT)
async def upload_contract(request: Request, response: Response,
                          project_id: uuid.UUID, is_scope: bool = False,
                          file: UploadFile = File(...),
                          user: User = Depends(get_current_user),
                          session: Session = Depends(get_db)) -> ProjectOut:
    project = _load_project(session, user, project_id)
    text = parsing.extract_text(file.filename or "", await _read_capped(file, MAX_CONTRACT_BYTES))
    if is_scope:
        project_service.set_contract(session, project, scope_text=text)
    else:
        project_service.set_contract(session, project, contract_text=text)
    return _out(project)


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
    rows = parsing.parse_comms_csv(await _read_capped(file, MAX_CSV_BYTES))
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
    rows = parsing.parse_rfi_csv(await _read_capped(file, MAX_CSV_BYTES))
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
    rows = parsing.parse_site_instructions_csv(await _read_capped(file, MAX_CSV_BYTES))
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
    rows = parsing.parse_meeting_minutes_csv(await _read_capped(file, MAX_CSV_BYTES))
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
    if not (project.contract_text or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "project has no contract_text; upload a contract before analyzing")
    job = jobs.enqueue_analysis(
        session, company_id=project.company_id, project_id=project.id, created_by=user.id,
    )
    return AnalyzeResponse(job_id=str(job.id), status=job.status.value)
