"""Commercial review endpoints (.14): queue, detail, approve/reject, comments."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.auth.deps import ensure_member, get_current_user, get_db
from app.models import Project, ReviewStatus, User, Variation
from app.services import review as review_service

router = APIRouter(tags=["review"])


# ---- schemas -------------------------------------------------------------
class VariationSummary(BaseModel):
    id: str
    title: str
    confidence_score: float
    confidence_band: str | None = None
    time_bar_risk: bool = False
    review_status: str
    amount: float | None = None


class EvidenceOut(BaseModel):
    type: str
    source_document_id: str | None = None
    reference: str | None = None
    quote: str | None = None


class ValueOut(BaseModel):
    amount: float | None = None
    estimate_low: float | None = None
    estimate_high: float | None = None
    currency: str = "AUD"
    basis_quality: str | None = None
    confidence: str | None = None


class CommentOut(BaseModel):
    id: str
    body: str
    author_user_id: str | None = None
    created_at: str


class VariationDetail(VariationSummary):
    description: str | None = None
    confidence_factors: dict | None = None
    reviewed_by: str | None = None
    evidence: list[EvidenceOut] = []
    value: ValueOut | None = None
    comments: list[CommentOut] = []


class ReviewAction(BaseModel):
    status: ReviewStatus            # confirmed | rejected | pending (reopen)


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)

    @field_validator("body")
    @classmethod
    def _strip_body(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("body must not be blank")
        return v


# ---- helpers -------------------------------------------------------------
def _summary(v: Variation, amount=None) -> VariationSummary:
    return VariationSummary(
        id=str(v.id), title=v.title, confidence_score=float(v.confidence_score),
        confidence_band=v.confidence_band.value if v.confidence_band else None,
        time_bar_risk=bool(v.time_bar_risk), review_status=v.review_status.value,
        amount=amount,
    )


def _load(session, user, variation_id) -> Variation:
    """Load a variation and enforce org membership (404 if not found/visible)."""
    v = session.get(Variation, variation_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "variation not found")
    ensure_member(session, user, v.company_id)
    return v


# ---- endpoints -----------------------------------------------------------
@router.get("/projects/{project_id}/review-queue", response_model=list[VariationSummary])
def review_queue(project_id: uuid.UUID, company_id: uuid.UUID | None = None,
                 review_status: ReviewStatus = ReviewStatus.pending,
                 user: User = Depends(get_current_user),
                 session: Session = Depends(get_db)) -> list[VariationSummary]:
    # Object-level authorization: derive the owning org from the project
    # itself, never from a caller-supplied company_id (kept optional, ignored,
    # for backward compatibility with existing callers that still send it).
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    ensure_member(session, user, project.company_id)
    rows = review_service.review_queue(session, project.company_id, project_id=project_id,
                                       status=review_status)
    return [_summary(v) for v in rows]


@router.get("/variations/{variation_id}", response_model=VariationDetail)
def variation_detail(variation_id: uuid.UUID, user: User = Depends(get_current_user),
                     session: Session = Depends(get_db)) -> VariationDetail:
    v = _load(session, user, variation_id)
    d = review_service.variation_detail(session, v)
    val = d["value"]
    return VariationDetail(
        **_summary(v, amount=float(val.amount) if val and val.amount is not None else None).model_dump(),
        description=v.description,
        confidence_factors=v.confidence_factors,
        reviewed_by=str(v.reviewed_by) if v.reviewed_by else None,
        evidence=[EvidenceOut(type=e.source_type.value,
                              source_document_id=str(e.source_document_id) if e.source_document_id else None,
                              reference=e.reference, quote=e.quote) for e in d["evidence"]],
        value=ValueOut(
            amount=float(val.amount) if val and val.amount is not None else None,
            estimate_low=float(val.estimate_low) if val and val.estimate_low is not None else None,
            estimate_high=float(val.estimate_high) if val and val.estimate_high is not None else None,
            currency=val.currency if val else "AUD",
            basis_quality=val.basis_quality.value if val and val.basis_quality else None,
            confidence=val.confidence.value if val and val.confidence else None,
        ) if val else None,
        comments=[CommentOut(id=str(c.id), body=c.body,
                             author_user_id=str(c.author_user_id) if c.author_user_id else None,
                             created_at=c.created_at.isoformat() if c.created_at else "")
                  for c in d["comments"]],
    )


@router.post("/variations/{variation_id}/review", response_model=VariationSummary)
def review_variation(variation_id: uuid.UUID, action: ReviewAction,
                     user: User = Depends(get_current_user),
                     session: Session = Depends(get_db)) -> VariationSummary:
    v = _load(session, user, variation_id)
    try:
        review_service.set_review_status(session, v, user=user, new_status=action.status)
    except review_service.InvalidTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"invalid transition: {exc}")
    return _summary(v)


@router.get("/variations/{variation_id}/comments", response_model=list[CommentOut])
def list_comments(variation_id: uuid.UUID, user: User = Depends(get_current_user),
                  session: Session = Depends(get_db)) -> list[CommentOut]:
    v = _load(session, user, variation_id)
    return [CommentOut(id=str(c.id), body=c.body,
                       author_user_id=str(c.author_user_id) if c.author_user_id else None,
                       created_at=c.created_at.isoformat() if c.created_at else "")
            for c in review_service.list_comments(session, v.id)]


@router.post("/variations/{variation_id}/comments", response_model=CommentOut,
             status_code=status.HTTP_201_CREATED)
def add_comment(variation_id: uuid.UUID, payload: CommentIn,
                user: User = Depends(get_current_user),
                session: Session = Depends(get_db)) -> CommentOut:
    v = _load(session, user, variation_id)
    if not payload.body.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "comment body is empty")
    c = review_service.add_comment(session, v, user=user, body=payload.body)
    return CommentOut(id=str(c.id), body=c.body,
                      author_user_id=str(c.author_user_id) if c.author_user_id else None,
                      created_at=c.created_at.isoformat() if c.created_at else "")
