"""Dashboard endpoints (.16): org overview + per-project rollups (org-scoped)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.deps import ensure_member, get_current_user, get_db
from app.models import Project, User
from app.services import dashboard as dashboard_service

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def org_dashboard(company_id: uuid.UUID, user: User = Depends(get_current_user),
                  session: Session = Depends(get_db)) -> dict:
    ensure_member(session, user, company_id)
    return dashboard_service.org_overview(session, company_id)


@router.get("/projects/{project_id}/dashboard")
def project_dashboard(project_id: uuid.UUID, user: User = Depends(get_current_user),
                      session: Session = Depends(get_db)) -> dict:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    ensure_member(session, user, project.company_id)
    return dashboard_service.project_dashboard(session, project.company_id, project)
