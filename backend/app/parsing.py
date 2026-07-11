"""File ingestion utilities (ported from the engine's parsing.py).

PDF/text extraction for contract & scope, and a forgiving comms-export CSV
reader (SMS/WhatsApp/email dumps). No LLM here. Generic utility, not engine IP.
"""
from __future__ import annotations

import csv
import io

from app.models import SourceType

# Defensive hard cap on register CSV row count — the 10MB upload byte cap
# (app/routers/projects.py's MAX_CSV_BYTES) doesn't bound row count on its
# own (a 10MB file of minimal rows can still be hundreds of thousands of
# rows), and each row becomes its own DB insert + object-storage PUT with no
# batching (app/services/projects.py's add_document, called once per row).
# Well above any realistic register size; exists purely to bound the worst
# case (security hardening pass).
MAX_CSV_ROWS = 5000


class CsvTooManyRows(ValueError):
    pass


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


def _header_picker(reader: csv.DictReader):
    """Return a pick(row, aliases) closure matching headers case-insensitively."""
    headers = {(h or "").lower().strip(): h for h in (reader.fieldnames or [])}

    def pick(row: dict, aliases: list[str]) -> str | None:
        for alias in aliases:
            if alias in headers:
                val = row.get(headers[alias])
                if val not in (None, ""):
                    return str(val).strip()
        return None

    return pick


# Canonical RFI field -> column-name aliases a real RFI register might use.
_RFI_ALIASES: dict[str, list[str]] = {
    "number": ["rfi_number", "rfi_no", "rfi", "number", "no", "ref", "reference", "id"],
    "subject": ["subject", "title", "topic", "description", "summary"],
    "question": ["question", "query", "detail", "details", "body", "request"],
    "response": ["response", "answer", "reply", "resolution", "outcome"],
    "date_raised": ["date_raised", "raised", "date", "submitted", "created", "opened", "issued"],
    "date_responded": ["date_responded", "responded", "answered", "closed", "resolved", "returned"],
    "status": ["status", "state"],
}


def _render_rfi(number, subject, question, response, raised, responded, status) -> str:
    lines = [f"RFI {number}" + (f" — {subject}" if subject else "")]
    if status:
        lines.append(f"Status: {status}")
    if raised or responded:
        lines.append(f"Raised: {raised or 'n/a'}  Responded: {responded or 'n/a'}")
    if question:
        lines.append(f"Question: {question}")
    if response:
        lines.append(f"Response: {response}")
    return "\n".join(lines)


def parse_rfi_csv(data: bytes) -> list[dict]:
    """Parse an RFI register CSV into document dicts (ref/occurred_at/status/text).

    Columns matched case-insensitively against common aliases. A row is skipped
    only if it has no subject, question, or response (i.e. it's blank).
    """
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    pick = _header_picker(reader)

    out: list[dict] = []
    for i, row in enumerate(reader):
        if i >= MAX_CSV_ROWS:
            raise CsvTooManyRows(f"CSV exceeds the {MAX_CSV_ROWS}-row limit")
        subject = pick(row, _RFI_ALIASES["subject"])
        question = pick(row, _RFI_ALIASES["question"])
        response = pick(row, _RFI_ALIASES["response"])
        if not (subject or question or response):
            continue
        number = pick(row, _RFI_ALIASES["number"]) or f"RFI-{i + 1}"
        raised = pick(row, _RFI_ALIASES["date_raised"])
        responded = pick(row, _RFI_ALIASES["date_responded"])
        status = pick(row, _RFI_ALIASES["status"])
        out.append({
            "ref": number,
            "occurred_at": raised,
            "status": status,
            "text": _render_rfi(number, subject, question, response, raised, responded, status),
        })
    return out


# Canonical site-instruction field -> column aliases (architect/engineer/superintendent directions).
_SITE_INSTRUCTION_ALIASES: dict[str, list[str]] = {
    "number": ["si_number", "si_no", "si", "instruction_number", "instruction_no",
               "number", "no", "ref", "reference", "id"],
    "date_issued": ["date_issued", "date", "issued", "date_raised", "created", "when"],
    "issued_by": ["issued_by", "from", "author", "superintendent", "architect", "engineer", "by"],
    "instruction": ["instruction", "description", "detail", "details", "direction",
                    "work", "scope", "body", "text"],
    "reference": ["reference", "drawing", "drawing_ref", "spec", "clause"],
    "status": ["status", "state"],
}


def _render_site_instruction(number, date_issued, issued_by, instruction, reference, status) -> str:
    lines = [f"Site Instruction {number}"]
    meta = []
    if date_issued:
        meta.append(f"Issued: {date_issued}")
    if issued_by:
        meta.append(f"By: {issued_by}")
    if reference:
        meta.append(f"Ref: {reference}")
    if status:
        meta.append(f"Status: {status}")
    if meta:
        lines.append("  ".join(meta))
    if instruction:
        lines.append(f"Instruction: {instruction}")
    return "\n".join(lines)


def parse_site_instructions_csv(data: bytes) -> list[dict]:
    """Parse a site-instruction register CSV into document dicts.

    Columns matched case-insensitively against common aliases; a row is skipped
    only when it carries no instruction text.
    """
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    pick = _header_picker(reader)

    out: list[dict] = []
    for i, row in enumerate(reader):
        if i >= MAX_CSV_ROWS:
            raise CsvTooManyRows(f"CSV exceeds the {MAX_CSV_ROWS}-row limit")
        instruction = pick(row, _SITE_INSTRUCTION_ALIASES["instruction"])
        if not instruction:
            continue
        number = pick(row, _SITE_INSTRUCTION_ALIASES["number"]) or f"SI-{i + 1}"
        date_issued = pick(row, _SITE_INSTRUCTION_ALIASES["date_issued"])
        issued_by = pick(row, _SITE_INSTRUCTION_ALIASES["issued_by"])
        reference = pick(row, _SITE_INSTRUCTION_ALIASES["reference"])
        status = pick(row, _SITE_INSTRUCTION_ALIASES["status"])
        out.append({
            "ref": number,
            "occurred_at": date_issued,
            "status": status,
            "text": _render_site_instruction(number, date_issued, issued_by,
                                             instruction, reference, status),
        })
    return out


# Canonical meeting-minute field -> column aliases (per minute item).
_MEETING_MINUTE_ALIASES: dict[str, list[str]] = {
    "number": ["item_number", "item_no", "item", "minute_no", "number", "no", "ref", "reference", "id"],
    "date": ["meeting_date", "date", "minutes_date", "held", "when"],
    "topic": ["topic", "subject", "title", "agenda", "heading"],
    "notes": ["notes", "discussion", "minute", "detail", "details", "body", "text"],
    "decision": ["decision", "resolution", "outcome"],
    "action": ["action", "action_item", "follow_up", "task"],
    "owner": ["owner", "responsible", "assignee", "by", "who"],
    "status": ["status", "state"],
}


def _render_meeting_minute(number, date, topic, notes, decision, action, owner, status) -> str:
    lines = [f"Meeting Minute {number}" + (f" — {topic}" if topic else "")]
    meta = []
    if date:
        meta.append(f"Date: {date}")
    if owner:
        meta.append(f"Owner: {owner}")
    if status:
        meta.append(f"Status: {status}")
    if meta:
        lines.append("  ".join(meta))
    if notes:
        lines.append(f"Notes: {notes}")
    if decision:
        lines.append(f"Decision: {decision}")
    if action:
        lines.append(f"Action: {action}")
    return "\n".join(lines)


def parse_meeting_minutes_csv(data: bytes) -> list[dict]:
    """Parse a meeting-minutes register CSV (one row per minute item).

    Columns matched case-insensitively against common aliases; a row is skipped
    only when it has no topic, notes, decision, or action (i.e. it's blank).
    """
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    pick = _header_picker(reader)

    out: list[dict] = []
    for i, row in enumerate(reader):
        if i >= MAX_CSV_ROWS:
            raise CsvTooManyRows(f"CSV exceeds the {MAX_CSV_ROWS}-row limit")
        topic = pick(row, _MEETING_MINUTE_ALIASES["topic"])
        notes = pick(row, _MEETING_MINUTE_ALIASES["notes"])
        decision = pick(row, _MEETING_MINUTE_ALIASES["decision"])
        action = pick(row, _MEETING_MINUTE_ALIASES["action"])
        if not (topic or notes or decision or action):
            continue
        number = pick(row, _MEETING_MINUTE_ALIASES["number"]) or f"MIN-{i + 1}"
        date = pick(row, _MEETING_MINUTE_ALIASES["date"])
        owner = pick(row, _MEETING_MINUTE_ALIASES["owner"])
        status = pick(row, _MEETING_MINUTE_ALIASES["status"])
        out.append({
            "ref": number,
            "occurred_at": date,
            "status": status,
            "text": _render_meeting_minute(number, date, topic, notes, decision,
                                           action, owner, status),
        })
    return out


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
        if i >= MAX_CSV_ROWS:
            raise CsvTooManyRows(f"CSV exceeds the {MAX_CSV_ROWS}-row limit")
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
