"""AI document parsing & normalization (engine ingest + baseline stage).

Turns a single raw construction communication into a NormalizedDocument using
Claude with structured outputs. Australia-only, all trades.

SDK notes (per the claude-api reference):
  * model claude-opus-4-8
  * adaptive thinking ({"type": "adaptive"}) — this is a reasoning-heavy extraction
  * structured outputs via output_config.format = {"type": "json_schema", ...}
  * no temperature/top_p (removed on Opus 4.8)

The Anthropic client is injected (typed as a minimal Protocol) so this module is
unit-testable without a live API key and without importing the SDK at import time.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from app.ai.normalization.dates import normalize_date
from app.ai.normalization.schema import NormalizedDocument

if TYPE_CHECKING:  # avoid a hard runtime dependency on the SDK for tests
    from anthropic import Anthropic

MODEL = "claude-opus-4-8"
MAX_TOKENS = 4096

SYSTEM = (
    "You normalize Australian construction project communications into structured data.\n"
    "Context: Australia only, all building/construction trades (electrical, plumbing, HVAC, "
    "carpentry, mechanical, civil, general building). The goal is to surface work or scope "
    "changes that may be legitimate but unclaimed/undocumented variations.\n\n"
    "Rules:\n"
    "- Interpret all dates DAY-FIRST (Australian convention: DD/MM/YYYY) and output ISO-8601.\n"
    "- Extract parties, references (RFIs, drawings, specs, variation/VO numbers, contract clauses, POs), "
    "and discrete scope_items.\n"
    "- Mark potential_variation=true ONLY when an item plausibly represents out-of-contract or "
    "additional work that may not have been formally claimed. Be conservative: do not flag routine, "
    "in-scope work.\n"
    "- Do not invent facts. If a field is unknown, omit it or use null/empty.\n"
    "- Return only the structured object."
)


class MessagesClient(Protocol):
    """Minimal surface of anthropic.Anthropic used here (for typing + test fakes)."""

    @property
    def messages(self) -> Any: ...


def _build_user_prompt(document_id: str, source_type: str, source: str | None,
                       timestamp: str | None, content: str) -> str:
    header = [f"document_id: {document_id}", f"source_type: {source_type}"]
    if source:
        header.append(f"source: {source}")
    if timestamp:
        header.append(f"timestamp: {timestamp}")
    return (
        "Normalize the following construction communication.\n\n"
        + "\n".join(header)
        + "\n\n--- CONTENT ---\n"
        + content
    )


def _output_format() -> dict:
    return {"type": "json_schema", "schema": NormalizedDocument.model_json_schema()}


def _extract_text(response: Any) -> str:
    return "".join(
        getattr(block, "text", "") for block in response.content
        if getattr(block, "type", None) == "text"
    )


def parse_document(
    client: "Anthropic | MessagesClient",
    *,
    document_id: str,
    source_type: str,
    content: str,
    source: str | None = None,
    timestamp: str | None = None,
) -> NormalizedDocument:
    """Normalize one raw document into a NormalizedDocument."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        system=SYSTEM,
        messages=[{
            "role": "user",
            "content": _build_user_prompt(document_id, source_type, source, timestamp, content),
        }],
        output_config={"format": _output_format()},
    )
    doc = NormalizedDocument.model_validate_json(_extract_text(response))
    return _post_normalize(doc)


def _post_normalize(doc: NormalizedDocument) -> NormalizedDocument:
    """Deterministic clean-up the model shouldn't be trusted to do perfectly."""
    doc.event_date = normalize_date(doc.event_date)
    for item in doc.scope_items:
        item.mentioned_date = normalize_date(item.mentioned_date)
    return doc
