"""Audit trail & evidence viewer endpoints (.17)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import ensure_member, get_current_user, get_db, require_admin
from app.models import User, Variation
from app.services import audit as audit_service
from app.services import billing as billing_service

router = APIRouter(tags=["audit"])


class AuditOut(BaseModel):
    id: str
    actor_user_id: str | None = None
    entity_type: str
    entity_id: str
    action: str
    before: dict | None = None
    after: dict | None = None
    created_at: str


class SourceDocumentOut(BaseModel):
    id: str
    source_type: str
    source: str | None = None
    doc_timestamp: str | None = None


class EvidenceContextOut(BaseModel):
    type: str
    reference: str | None = None
    quote: str | None = None
    source_document: SourceDocumentOut | None = None


def _audit_out(a) -> AuditOut:
    return AuditOut(
        id=str(a.id), actor_user_id=str(a.actor_user_id) if a.actor_user_id else None,
        entity_type=a.entity_type, entity_id=str(a.entity_id), action=a.action,
        before=a.before, after=a.after,
        created_at=a.created_at.isoformat() if a.created_at else "",
    )


def _load_variation(session, user, variation_id) -> Variation:
    v = session.get(Variation, variation_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "variation not found")
    ensure_member(session, user, v.company_id)
    return v


# -- org audit trail (admin only) -----------------------------------------
@router.get("/audit", response_model=list[AuditOut])
def org_audit(company_id: uuid.UUID, entity_type: str | None = None,
              # Clamped: an attacker-controlled limit must not be able to
              # force an arbitrarily large result set into memory.
              limit: int = Query(100, ge=1, le=500),
              user: User = Depends(get_current_user),
              session: Session = Depends(get_db)) -> list[AuditOut]:
    require_admin(session, user, company_id)
    try:
        billing_service.enforce_feature(session, company_id, "audit_log")
    except billing_service.FeatureNotAvailable as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
    rows = audit_service.list_audit(session, company_id, entity_type=entity_type, limit=limit)
    return [_audit_out(a) for a in rows]


# -- per-variation audit history (any member) -----------------------------
@router.get("/variations/{variation_id}/audit", response_model=list[AuditOut])
def variation_audit(variation_id: uuid.UUID, user: User = Depends(get_current_user),
                    session: Session = Depends(get_db)) -> list[AuditOut]:
    v = _load_variation(session, user, variation_id)
    rows = audit_service.list_audit(session, v.company_id, entity_type="variation",
                                    entity_id=variation_id)
    return [_audit_out(a) for a in rows]


# -- evidence viewer with source-document context (any member) ------------
@router.get("/variations/{variation_id}/evidence", response_model=list[EvidenceContextOut])
def variation_evidence(variation_id: uuid.UUID, user: User = Depends(get_current_user),
                       session: Session = Depends(get_db)) -> list[EvidenceContextOut]:
    v = _load_variation(session, user, variation_id)
    pairs = audit_service.evidence_with_documents(session, v.id)
    out: list[EvidenceContextOut] = []
    for e, d in pairs:
        out.append(EvidenceContextOut(
            type=e.source_type.value, reference=e.reference, quote=e.quote,
            source_document=None if d is None else SourceDocumentOut(
                id=str(d.id), source_type=d.source_type.value, source=d.source,
                doc_timestamp=d.doc_timestamp.isoformat() if d.doc_timestamp else None,
            ),
        ))
    return out
