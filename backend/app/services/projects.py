"""Project + document service — org-scoped CRUD and upload intake.

All reads/writes are scoped by company_id (org isolation). Uploaded contract /
scope text lands on the Project (engine baseline inputs, contract v1.2); comms
documents are stored and registered as Document rows for later analysis.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Document, Project, ProjectStatus, SourceType, User


def create_project(
    session: Session,
    *,
    company_id: uuid.UUID,
    created_by: uuid.UUID | None,
    name: str,
    contract_text: str | None = None,
    scope_text: str | None = None,
    state: str | None = None,
    status: ProjectStatus = ProjectStatus.in_progress,
) -> Project:
    project = Project(
        id=uuid.uuid4(),
        company_id=company_id,
        name=name,
        contract_text=contract_text,
        scope_text=scope_text,
        state=state,
        status=status,
        created_by=created_by,
    )
    session.add(project)
    session.commit()
    return project


def list_projects(session: Session, company_id: uuid.UUID, *,
                  archived: bool = False) -> list[Project]:
    """Active projects by default; archived=True lists only archived ones."""
    stmt = select(Project).where(Project.company_id == company_id)
    stmt = stmt.where(Project.archived_at.is_not(None) if archived
                      else Project.archived_at.is_(None))
    return list(session.execute(
        stmt.order_by(Project.created_at.desc())
    ).scalars().all())


def archive_project(session: Session, project: Project, *, actor: User) -> Project:
    """Soft-archive: hidden from the default dashboard/list, fully recoverable."""
    if project.archived_at is None:
        project.archived_at = datetime.now(timezone.utc)
        session.add(AuditLog(
            company_id=project.company_id, actor_user_id=actor.id,
            entity_type="project", entity_id=project.id, action="project.archived",
            before={"archived": False}, after={"archived": True},
        ))
        session.commit()
    return project


def unarchive_project(session: Session, project: Project, *, actor: User) -> Project:
    """Restore an archived project to the active dashboard."""
    if project.archived_at is not None:
        project.archived_at = None
        session.add(AuditLog(
            company_id=project.company_id, actor_user_id=actor.id,
            entity_type="project", entity_id=project.id, action="project.unarchived",
            before={"archived": True}, after={"archived": False},
        ))
        session.commit()
    return project


def delete_project(session: Session, project: Project, *, actor: User) -> None:
    """PERMANENT delete — admin-only at the router. Irreversible.

    A single core DELETE lets the DB-level ON DELETE CASCADE chains remove
    documents, analysis jobs, variations, evidence, value estimates and
    comments atomically. The audit row survives on purpose (no FK to
    projects): the org keeps a record that the project was deleted, by whom.
    """
    session.add(AuditLog(
        company_id=project.company_id, actor_user_id=actor.id,
        entity_type="project", entity_id=project.id, action="project.deleted",
        before={"name": project.name, "status": project.status.value},
        after=None,
    ))
    session.execute(delete(Project).where(Project.id == project.id))
    session.commit()


def get_project(session: Session, company_id: uuid.UUID, project_id: uuid.UUID) -> Project | None:
    return session.execute(
        select(Project).where(Project.id == project_id, Project.company_id == company_id)
    ).scalar_one_or_none()


def set_contract(session: Session, project: Project, *,
                 contract_text: str | None = None, scope_text: str | None = None) -> Project:
    if contract_text is not None:
        project.contract_text = contract_text
    if scope_text is not None:
        project.scope_text = scope_text
    session.commit()
    return project


def add_document(
    session: Session,
    store,                       # DocumentLoader/-Store with .put(key, data)
    *,
    company_id: uuid.UUID,
    project_id: uuid.UUID,
    source_type: SourceType,
    content: str,
    source: str | None = None,
    occurred_at: str | None = None,
) -> Document:
    doc_id = uuid.uuid4()
    storage_key = f"{company_id}/{project_id}/docs/{doc_id}.txt"
    store.put(storage_key, content)
    document = Document(
        id=doc_id,
        company_id=company_id,
        project_id=project_id,
        source_type=source_type,
        doc_timestamp=_parse_dt(occurred_at),
        source=source,
        storage_key=storage_key,
    )
    session.add(document)
    session.commit()
    return document


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
