"""Variation review report (.15) — aggregate data for web + PDF.

Builds a commercial-review report for one project: the contract baseline (AU SoP
context), the selected variations with evidence + value, and recoverable totals.
Default selection is `confirmed` variations (the claim candidates).
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AnalysisJob,
    Evidence,
    Project,
    ReviewStatus,
    ValueEstimate,
    Variation,
)


def build_report(session: Session, *, company_id: uuid.UUID, project: Project,
                 status: ReviewStatus | None = ReviewStatus.confirmed) -> dict:
    latest_job = session.execute(
        select(AnalysisJob)
        .where(AnalysisJob.project_id == project.id, AnalysisJob.company_id == company_id)
        .order_by(AnalysisJob.created_at.desc()).limit(1)
    ).scalar_one_or_none()

    stmt = select(Variation).where(
        Variation.project_id == project.id, Variation.company_id == company_id
    )
    if status is not None:
        stmt = stmt.where(Variation.review_status == status)
    variations = list(session.execute(
        stmt.order_by(Variation.confidence_score.desc())
    ).scalars().all())

    values = {
        ve.variation_id: ve for ve in session.execute(
            select(ValueEstimate).join(Variation, Variation.id == ValueEstimate.variation_id)
            .where(Variation.project_id == project.id)
        ).scalars().all()
    }
    evid_counts = Counter(
        e.variation_id for e in session.execute(
            select(Evidence).join(Variation, Variation.id == Evidence.variation_id)
            .where(Variation.project_id == project.id)
        ).scalars().all()
    )

    items, total = [], Decimal("0")
    for v in variations:
        ve = values.get(v.id)
        if ve is not None and ve.amount is not None:
            total += ve.amount
        items.append({
            "id": str(v.id),
            "title": v.title,
            "description": v.description,
            "confidence_score": float(v.confidence_score),
            "confidence_band": v.confidence_band.value if v.confidence_band else None,
            "time_bar_risk": bool(v.time_bar_risk),
            "review_status": v.review_status.value,
            "evidence_count": evid_counts.get(v.id, 0),
            "value": None if ve is None else {
                "amount": float(ve.amount) if ve.amount is not None else None,
                "estimate_low": float(ve.estimate_low) if ve.estimate_low is not None else None,
                "estimate_high": float(ve.estimate_high) if ve.estimate_high is not None else None,
                "currency": ve.currency,
                "basis_quality": ve.basis_quality.value if ve.basis_quality else None,
                "confidence": ve.confidence.value if ve.confidence else None,
            },
        })

    return {
        "project": {"id": str(project.id), "name": project.name,
                    "state": project.state, "status": project.status.value},
        "baseline": latest_job.baseline if latest_job else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status_filter": status.value if status else "all",
        "summary": {
            "variation_count": len(items),
            "recoverable_total": float(total),
            "currency": "AUD",
            "time_bar_at_risk": sum(1 for i in items if i["time_bar_risk"]),
        },
        "variations": items,
    }
