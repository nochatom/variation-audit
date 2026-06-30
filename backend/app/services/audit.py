"""Audit trail & evidence viewer (.17).

Reads the immutable audit_log (written by the review and org services) and pairs
variation evidence with its source documents so a reviewer can inspect each
finding in context. Read-only — the audit log is append-only by design.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Document, Evidence


def list_audit(session: Session, company_id: uuid.UUID, *,
               entity_type: str | None = None, entity_id: uuid.UUID | None = None,
               limit: int = 100) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.company_id == company_id)
    if entity_type is not None:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
    return list(session.execute(stmt).scalars().all())


def evidence_with_documents(session: Session,
                            variation_id: uuid.UUID) -> list[tuple[Evidence, Document | None]]:
    """Each evidence item paired with its source document (or None)."""
    evidence = list(session.execute(
        select(Evidence).where(Evidence.variation_id == variation_id)
        .order_by(Evidence.created_at)
    ).scalars().all())
    doc_ids = [e.source_document_id for e in evidence if e.source_document_id]
    docs: dict[uuid.UUID, Document] = {
        d.id: d for d in session.execute(
            select(Document).where(Document.id.in_(doc_ids))
        ).scalars().all()
    }
    return [(e, docs.get(e.source_document_id) if e.source_document_id else None) for e in evidence]
