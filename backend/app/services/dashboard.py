"""Dashboard aggregation (.16) — org overview + per-project rollups.

Provides the data a dashboard UI renders: per-project variation counts by review
status, confirmed recoverable totals, time-bar exposure, and latest-job status,
plus entry-point links into the review queue and reports.
"""
from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AnalysisJob,
    Document,
    Project,
    ReviewStatus,
    ValueEstimate,
    Variation,
)


def _status_counts(variations) -> dict:
    c = Counter(v.review_status.value for v in variations)
    return {
        "pending": c.get("pending", 0),
        "confirmed": c.get("confirmed", 0),
        "rejected": c.get("rejected", 0),
        "total": len(variations),
    }


def org_overview(session: Session, company_id: uuid.UUID) -> dict:
    projects = list(session.execute(
        select(Project).where(Project.company_id == company_id)
        .order_by(Project.created_at.desc())
    ).scalars().all())
    variations = list(session.execute(
        select(Variation).where(Variation.company_id == company_id)
    ).scalars().all())
    confirmed_values = list(session.execute(
        select(ValueEstimate).join(Variation, Variation.id == ValueEstimate.variation_id)
        .where(Variation.company_id == company_id,
               Variation.review_status == ReviewStatus.confirmed)
    ).scalars().all())

    var_project = {v.id: v.project_id for v in variations}
    by_project = defaultdict(list)
    for v in variations:
        by_project[v.project_id].append(v)
    recoverable = defaultdict(Decimal)
    for ve in confirmed_values:
        pid = var_project.get(ve.variation_id)
        if pid is not None and ve.amount is not None:
            recoverable[pid] += ve.amount

    rows = []
    for p in projects:
        pv = by_project.get(p.id, [])
        rows.append({
            "id": str(p.id), "name": p.name, "status": p.status.value,
            "has_contract": bool(p.contract_text),
            "counts": _status_counts(pv),
            "recoverable_confirmed": float(recoverable.get(p.id, 0)),
            "time_bar_at_risk": sum(1 for v in pv if v.time_bar_risk),
            "links": {"review_queue": f"/projects/{p.id}/review-queue?company_id={company_id}",
                      "report": f"/projects/{p.id}/report"},
        })

    return {
        "company_id": str(company_id),
        "totals": {
            "projects": len(projects),
            "pending": sum(r["counts"]["pending"] for r in rows),
            "confirmed": sum(r["counts"]["confirmed"] for r in rows),
            "recoverable_confirmed": float(sum(recoverable.values())),
            "currency": "AUD",
        },
        "projects": rows,
    }


def project_dashboard(session: Session, company_id: uuid.UUID, project: Project) -> dict:
    variations = list(session.execute(
        select(Variation).where(Variation.project_id == project.id,
                                Variation.company_id == company_id)
    ).scalars().all())
    confirmed_values = list(session.execute(
        select(ValueEstimate).join(Variation, Variation.id == ValueEstimate.variation_id)
        .where(Variation.project_id == project.id,
               Variation.review_status == ReviewStatus.confirmed)
    ).scalars().all())
    latest_job = session.execute(
        select(AnalysisJob).where(AnalysisJob.project_id == project.id)
        .order_by(AnalysisJob.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    doc_count = len(list(session.execute(
        select(Document).where(Document.project_id == project.id)
    ).scalars().all()))

    recoverable = sum((ve.amount for ve in confirmed_values if ve.amount is not None), Decimal("0"))

    return {
        "project": {"id": str(project.id), "name": project.name, "state": project.state,
                    "status": project.status.value, "has_contract": bool(project.contract_text)},
        "counts": _status_counts(variations),
        "recoverable_confirmed": float(recoverable),
        "currency": "AUD",
        "time_bar_at_risk": sum(1 for v in variations if v.time_bar_risk),
        "document_count": doc_count,
        "latest_job": None if latest_job is None else {
            "id": str(latest_job.id), "status": latest_job.status.value,
            "recoverable_total": float(latest_job.recoverable_total)
            if latest_job.recoverable_total is not None else None,
            "baseline": latest_job.baseline,
        },
        "links": {
            "review_queue": f"/projects/{project.id}/review-queue?company_id={company_id}",
            "report": f"/projects/{project.id}/report",
            "report_pdf": f"/projects/{project.id}/report.pdf",
            "analyze": f"/projects/{project.id}/analyze",
        },
    }
