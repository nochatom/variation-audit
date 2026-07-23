"""Report endpoints (.15): web (JSON) + PDF export of the variation review report."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth.deps import ensure_member, get_current_user, get_db
from app.models import Project, ReviewStatus, User
from app.posthog_client import posthog_client
from app.reports_pdf import render_report_pdf
from app.services import billing as billing_service
from app.services import reports as report_service

router = APIRouter(prefix="/projects/{project_id}", tags=["reports"])


def _load(session, user, project_id) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    ensure_member(session, user, project.company_id)
    return project


@router.get("/report")
def report_json(project_id: uuid.UUID, review_status: ReviewStatus | None = ReviewStatus.confirmed,
                user: User = Depends(get_current_user),
                session: Session = Depends(get_db)) -> dict:
    project = _load(session, user, project_id)
    return report_service.build_report(session, company_id=project.company_id,
                                       project=project, status=review_status)


@router.get("/report.pdf")
def report_pdf(project_id: uuid.UUID, review_status: ReviewStatus | None = ReviewStatus.confirmed,
               user: User = Depends(get_current_user),
               session: Session = Depends(get_db)) -> Response:
    project = _load(session, user, project_id)
    try:
        billing_service.enforce_feature(session, project.company_id, "exports")
    except billing_service.FeatureNotAvailable as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    data = report_service.build_report(session, company_id=project.company_id,
                                       project=project, status=review_status)
    pdf = render_report_pdf(data)
    filename = f"variation-report-{project_id}.pdf"
    posthog_client.capture(
        "report_exported",
        distinct_id=str(user.id),
        properties={
            "review_status": review_status.value if review_status else None,
            "variation_count": len(data.get("variations", [])),
        },
    )
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
