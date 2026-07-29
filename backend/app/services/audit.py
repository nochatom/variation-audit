"""Audit trail & evidence viewer (.17).

Reads the immutable audit_log (written by the review and org services) and pairs
variation evidence with its source documents so a reviewer can inspect each
finding in context. Read-only — the audit log is append-only by design.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Document,
    Evidence,
    Invitation,
    Office,
    Organization,
    Project,
    User,
    Variation,
)

# Which model and attribute names each audited entity_type. An audit row stores
# only a UUID, so without this the trail can say "a3f2b891 did something to
# 8f31a204" and nothing more — which defeats the point of an audit trail.
# `membership` is deliberately User: orgs.py writes the TARGET user's id as the
# entity_id, not a membership row id.
_ENTITY_LABEL: dict[str, tuple[type, tuple[str, ...]]] = {
    "project": (Project, ("name",)),
    "variation": (Variation, ("title",)),
    "membership": (User, ("full_name", "email")),
    "invitation": (Invitation, ("email",)),
    "office": (Office, ("name",)),
    "organization": (Organization, ("name",)),
    "subscription": (Organization, ("name",)),
}


def _first_attr(obj, names: tuple[str, ...]) -> str | None:
    for n in names:
        v = getattr(obj, n, None)
        if v:
            return str(v)
    return None


def resolve_labels(session: Session, rows: list[AuditLog]) -> tuple[dict, dict]:
    """Human-readable names for the actors and entities in `rows`.

    Returns ({actor_user_id: name}, {(entity_type, entity_id): label}).

    Batched per model — one query for the actors and one per entity_type present,
    rather than two lookups per row. A 100-row page therefore costs at most a
    handful of queries regardless of how many distinct entities it touches.
    """
    # .scalars().all() rather than iterating .scalars(): that is the pattern used
    # throughout this module, and the test fakes implement .all() only.
    actor_ids = {r.actor_user_id for r in rows if r.actor_user_id}
    actors: dict = {}
    if actor_ids:
        for u in session.execute(select(User).where(User.id.in_(actor_ids))).scalars().all():
            actors[u.id] = _first_attr(u, ("full_name", "email")) or str(u.id)

    labels: dict = {}
    by_type: dict[str, set] = {}
    for r in rows:
        if r.entity_type in _ENTITY_LABEL:
            by_type.setdefault(r.entity_type, set()).add(r.entity_id)

    for etype, ids in by_type.items():
        model, attrs = _ENTITY_LABEL[etype]
        found = session.execute(select(model).where(model.id.in_(ids))).scalars().all()
        for obj in found:
            label = _first_attr(obj, attrs)
            if label:
                labels[(etype, obj.id)] = label

    return actors, labels


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
        .limit(2000)  # defensive hard cap, not pagination — security hardening pass
    ).scalars().all())
    doc_ids = [e.source_document_id for e in evidence if e.source_document_id]
    docs: dict[uuid.UUID, Document] = {
        d.id: d for d in session.execute(
            select(Document).where(Document.id.in_(doc_ids))
        ).scalars().all()
    }
    return [(e, docs.get(e.source_document_id) if e.source_document_id else None) for e in evidence]
