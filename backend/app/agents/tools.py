"""ADK tools: thin wrappers over existing Project/Document queries + storage.

ADK tools are plain functions with type hints and a docstring (sent to the
model as the tool description); they take no session/DB handle directly, so
each tool here is built by a factory that closes over the already-open
`Session` and `DocumentLoader` for one run — the exact same
`build_loader().load(document.storage_key)` call the worker already makes
(app/worker/job_worker.py:build_request), and the exact same `Project`/
`Document` queries. Factories, not classes, since ADK tools must be plain
callables.
"""
from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, Project


class DocumentLoader(Protocol):
    def load(self, storage_key: str) -> str: ...


def make_list_project_documents_tool(session: Session, loader: DocumentLoader, project_id: str):
    def list_project_documents() -> dict:
        """List every uploaded document for this project, with its content.

        Returns a dict with a "documents" list, each item having
        document_id, source_type, and content (raw extracted text).
        """
        docs = session.execute(
            select(Document).where(Document.project_id == project_id)
        ).scalars().all()
        return {
            "documents": [
                {
                    "document_id": str(d.id),
                    "source_type": d.source_type.value if hasattr(d.source_type, "value") else str(d.source_type),
                    "content": loader.load(d.storage_key),
                }
                for d in docs
            ]
        }

    return list_project_documents


def make_get_contract_baseline_tool(session: Session, project_id: str):
    def get_contract_baseline() -> dict:
        """Get this project's contract baseline: contract text, scope text, and AU state.

        Returns a dict with contract_text, scope_text, and state.
        """
        project = session.get(Project, project_id)
        return {
            "contract_text": (project.contract_text if project else None) or "",
            "scope_text": (project.scope_text if project else None) or "",
            "state": project.state if project else None,
        }

    return get_contract_baseline
