"""File ingestion utilities (ported from the engine's parsing.py).

PDF/text extraction for contract & scope, and a forgiving comms-export CSV
reader (SMS/WhatsApp/email dumps). No LLM here. Generic utility, not engine IP.
"""
from __future__ import annotations

import csv
import io

from app.models import SourceType

# Canonical field -> column-name aliases a real export might use.
_COMMS_ALIASES: dict[str, list[str]] = {
    "id": ["id", "message_id", "msg_id", "ref", "reference"],
    "kind": ["kind", "type", "channel", "source"],
    "author": ["author", "from", "sender", "name", "user"],
    "occurred_at": ["occurred_at", "date", "datetime", "timestamp", "sent", "when", "time"],
    "text": ["text", "body", "message", "content", "note", "comment"],
}

# Engine/export 'kind' -> product source_type (contract v1.2 vocabulary).
_KIND_TO_SOURCE: dict[str, SourceType] = {
    "email": SourceType.email,
    "rfi": SourceType.rfi,
    "sms": SourceType.sms,
    "minutes": SourceType.meeting_note,
    "meeting_note": SourceType.meeting_note,
    "site_instruction": SourceType.site_instruction,
    "daily_log": SourceType.document,
    "photo": SourceType.document,
    "document": SourceType.document,
}


def kind_to_source_type(kind: str | None) -> SourceType:
    return _KIND_TO_SOURCE.get((kind or "").lower().strip(), SourceType.document)


def extract_text(filename: str, data: bytes) -> str:
    """Extract plain text from an uploaded contract/scope file (PDF or text)."""
    if (filename or "").lower().endswith(".pdf"):
        return _pdf_text(data)
    return data.decode("utf-8-sig", errors="replace").strip()


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader  # lazy: only the PDF path needs it

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def parse_comms_csv(data: bytes) -> list[dict]:
    """Parse a comms-export CSV into document dicts (id/kind/author/occurred_at/text).

    Column names matched case-insensitively against common aliases; rows with no
    message text are skipped.
    """
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    headers = {(h or "").lower().strip(): h for h in (reader.fieldnames or [])}

    def pick(row: dict, field: str) -> str | None:
        for alias in _COMMS_ALIASES[field]:
            if alias in headers:
                val = row.get(headers[alias])
                if val not in (None, ""):
                    return val
        return None

    docs: list[dict] = []
    for i, row in enumerate(reader):
        body = pick(row, "text")
        if not body or not body.strip():
            continue
        docs.append({
            "id": pick(row, "id") or f"row-{i + 1}",
            "kind": (pick(row, "kind") or "email").lower(),
            "author": pick(row, "author"),
            "occurred_at": pick(row, "occurred_at"),
            "text": body,
        })
    return docs
