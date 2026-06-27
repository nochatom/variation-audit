"""Commercial review workflow (.14).

The human-in-the-loop layer over engine-detected variations: a review queue,
variation detail, approve/reject transitions (audited), and comments. All
operations are org-scoped by company_id.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Evidence,
    ReviewComment,
    ReviewStatus,
    User,
    ValueEstimate,
    Variation,
)

# Allowed review_status transitions. pending -> confirmed/rejected; either
# terminal state can be reopened to pending or flipped to the other.
_TRANSITIONS = {
    ReviewStatus.pending: {ReviewStatus.confirmed, ReviewStatus.rejected},
    ReviewStatus.confirmed: {ReviewStatus.rejected, ReviewStatus.pending},
    ReviewStatus.rejected: {ReviewStatus.confirmed, ReviewStatus.pending},
}


class InvalidTransition(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def review_queue(session: Session, company_id: uuid.UUID, *,
                 project_id: uuid.UUID | None = None,
                 status: ReviewStatus | None = ReviewStatus.pending) -> list[Variation]:
    """Variations awaiting (or filtered by) review, highest-value/-confidence first."""
    stmt = select(Variation).where(Variation.company_id == company_id)
    if project_id is not None:
        stmt = stmt.where(Variation.project_id == project_id)
    if status is not None:
        stmt = stmt.where(Variation.review_status == status)
    stmt = stmt.order_by(Variation.confidence_score.desc(), Variation.created_at.desc())
    return list(session.execute(stmt).scalars().all())


def get_variation(session: Session, company_id: uuid.UUID,
                  variation_id: uuid.UUID) -> Variation | None:
    return session.execute(
        select(Variation).where(
            Variation.id == variation_id, Variation.company_id == company_id
        )
    ).scalar_one_or_none()


def variation_detail(session: Session, variation: Variation) -> dict:
    evidence = list(session.execute(
        select(Evidence).where(Evidence.variation_id == variation.id)
    ).scalars().all())
    value = session.execute(
        select(ValueEstimate).where(ValueEstimate.variation_id == variation.id)
    ).scalar_one_or_none()
    comments = list_comments(session, variation.id)
    return {"variation": variation, "evidence": evidence, "value": value, "comments": comments}


def set_review_status(session: Session, variation: Variation, *, user: User,
                      new_status: ReviewStatus) -> Variation:
    current = variation.review_status
    if new_status == current or new_status not in _TRANSITIONS[current]:
        raise InvalidTransition(f"{current.value} -> {new_status.value}")

    variation.review_status = new_status
    if new_status == ReviewStatus.pending:           # reopened
        variation.reviewed_by = None
        variation.reviewed_at = None
        action = "review.reopened"
    else:
        variation.reviewed_by = user.id
        variation.reviewed_at = _now()
        action = f"review.{new_status.value}"

    session.add(AuditLog(
        company_id=variation.company_id, actor_user_id=user.id,
        entity_type="variation", entity_id=variation.id, action=action,
        before={"review_status": current.value},
        after={"review_status": new_status.value},
    ))
    session.commit()
    return variation


def add_comment(session: Session, variation: Variation, *, user: User, body: str) -> ReviewComment:
    comment = ReviewComment(
        company_id=variation.company_id, variation_id=variation.id,
        author_user_id=user.id, body=body,
    )
    session.add(comment)
    session.commit()
    return comment


def list_comments(session: Session, variation_id: uuid.UUID) -> list[ReviewComment]:
    return list(session.execute(
        select(ReviewComment).where(ReviewComment.variation_id == variation_id)
        .order_by(ReviewComment.created_at)
    ).scalars().all())
