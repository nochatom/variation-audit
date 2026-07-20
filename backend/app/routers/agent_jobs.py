"""Agent-scaffold analysis job endpoints (app/agents/) — separate from the
production /projects/{id}/analyze (engine-pipeline) endpoint. Creates an
AgentAnalysisJob row and returns immediately; app/agents/worker.py is the
consumer. Frontend polls GET .../status for progress and, once COMPLETED,
the persisted result.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.errors import safe_job_error_message
from app.agents.jobs import enqueue_agent_analysis
from app.auth.deps import ensure_member, get_current_user, get_db
from app.models import AgentAnalysisJob, Project, User
from app.posthog_client import posthog_client
from app.rate_limit import ANALYSIS_LIMIT, limiter

router = APIRouter(prefix="/projects/{project_id}/agent-analysis", tags=["agent-analysis"])


class AgentJobOut(BaseModel):
    job_id: str
    project_id: str
    status: str
    current_agent: str | None
    progress_percent: int
    error_code: str | None
    error_message: str | None
    result: dict | None
    created_at: str
    started_at: str | None
    completed_at: str | None

    @classmethod
    def from_job(cls, job: AgentAnalysisJob) -> "AgentJobOut":
        return cls(
            job_id=str(job.id),
            project_id=str(job.project_id),
            status=job.status.value,
            current_agent=job.current_agent,
            progress_percent=job.progress_percent,
            error_code=job.error_code,
            # Never the raw job.error_message column — that can hold a raw
            # litellm exception message or repr(exc) for an unexpected
            # failure (see app/agents/worker.py's fail_job calls). Map to a
            # generic, safe, user-facing message instead; the raw text stays
            # in the DB/logs only.
            error_message=safe_job_error_message(job.error_code),
            result=job.result,
            created_at=job.created_at.isoformat(),
            started_at=job.started_at.isoformat() if job.started_at else None,
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
        )


def _load_project(session: Session, user: User, project_id: uuid.UUID) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    ensure_member(session, user, project.company_id)
    return project


@router.post("", response_model=AgentJobOut, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(ANALYSIS_LIMIT)
def create_agent_analysis_job(
    request: Request,
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> AgentJobOut:
    project = _load_project(session, user, project_id)
    if not (project.contract_text or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "project has no contract_text; upload a contract before analyzing")
    job = enqueue_agent_analysis(
        session, company_id=project.company_id, project_id=project.id, created_by=user.id,
    )
    posthog_client.capture(
        "agent_analysis_started",
        distinct_id=str(user.id),
        properties={"job_id": str(job.id)},
    )
    return AgentJobOut.from_job(job)


@router.get("/{job_id}", response_model=AgentJobOut)
def get_agent_analysis_job(
    project_id: uuid.UUID,
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> AgentJobOut:
    _load_project(session, user, project_id)
    job = session.get(AgentAnalysisJob, job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent analysis job not found")
    return AgentJobOut.from_job(job)
