"""Project endpoints: create/list/get, contract & comms upload, analyze."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import parsing
from app.auth.deps import ensure_member, get_current_user, get_db
from app.models import Membership, Project, ProjectStatus, User
from app.services import jobs
from app.services import projects as project_service
from app.storage import build_loader

router = APIRouter(prefix="/projects", tags=["projects"])


# ---- schemas -------------------------------------------------------------
class CreateProjectRequest(BaseModel):
    company_id: uuid.UUID
    name: str
    contract_text: str | None = None
    scope_text: str | None = None
    state: str | None = None


class ProjectOut(BaseModel):
    id: str
    company_id: str
    name: str
    state: str | None = None
    status: str
    has_contract: bool = False


def _out(p) -> ProjectOut:
    return ProjectOut(id=str(p.id), company_id=str(p.company_id), name=p.name,
                      state=p.state, status=p.status.value,
                      has_contract=bool(p.contract_text))


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
def list_projects(company_id: uuid.UUID, user: User = Depends(get_current_user),
                  session: Session = Depends(get_db)) -> list[ProjectOut]:
    ensure_member(session, user, company_id)
    return [_out(p) for p in project_service.list_projects(session, company_id)]


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


@router.post("/{project_id}/contract", response_model=ProjectOut)
async def upload_contract(project_id: uuid.UUID, is_scope: bool = False,
                          file: UploadFile = File(...),
                          user: User = Depends(get_current_user),
                          session: Session = Depends(get_db)) -> ProjectOut:
    project = _load_project(session, user, project_id)
    text = parsing.extract_text(file.filename or "", await file.read())
    if is_scope:
        project_service.set_contract(session, project, scope_text=text)
    else:
        project_service.set_contract(session, project, contract_text=text)
    return _out(project)


class CommsUploadResponse(BaseModel):
    project_id: str
    documents_added: int


@router.post("/{project_id}/comms", response_model=CommsUploadResponse)
async def upload_comms(project_id: uuid.UUID, file: UploadFile = File(...),
                       user: User = Depends(get_current_user),
                       session: Session = Depends(get_db)) -> CommsUploadResponse:
    project = _load_project(session, user, project_id)
    rows = parsing.parse_comms_csv(await file.read())
    store = build_loader()
    for r in rows:
        project_service.add_document(
            session, store, company_id=project.company_id, project_id=project.id,
            source_type=parsing.kind_to_source_type(r.get("kind")),
            content=r["text"], source=r.get("author"), occurred_at=r.get("occurred_at"),
        )
    return CommsUploadResponse(project_id=str(project.id), documents_added=len(rows))


class AnalyzeResponse(BaseModel):
    job_id: str
    status: str


@router.post("/{project_id}/analyze", response_model=AnalyzeResponse,
             status_code=status.HTTP_202_ACCEPTED)
def analyze(project_id: uuid.UUID, user: User = Depends(get_current_user),
            session: Session = Depends(get_db)) -> AnalyzeResponse:
    project = _load_project(session, user, project_id)
    if not (project.contract_text or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "project has no contract_text; upload a contract before analyzing")
    job = jobs.enqueue_analysis(
        session, company_id=project.company_id, project_id=project.id, created_by=user.id,
    )
    return AnalyzeResponse(job_id=str(job.id), status=job.status.value)
