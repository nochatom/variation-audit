"""Validates (and attempts to repair) a model's raw text output against the
agent's declared output_schema, before app/agents/reliable_llm.py accepts
the response — this is what makes the primary/fallback model contract
enforcement in requirement #4 real: a malformed response, from *either*
model, is rejected here and retried via the exact same retry/fallback path
already built for provider failures, rather than a second mechanism.
"""
from __future__ import annotations

import json
import re

from pydantic import BaseModel

from app.agents.errors import AISchemaValidationError


def extract_text(response) -> str | None:
    """Pull the concatenated text out of an ADK LlmResponse, if any."""
    content = getattr(response, "content", None)
    if content is None or not getattr(content, "parts", None):
        return None
    texts = [p.text for p in content.parts if getattr(p, "text", None)]
    return "".join(texts) if texts else None


def _repair_candidates(text: str):
    """Yields progressively more aggressive parse attempts: raw text, then
    markdown-fence-stripped, then the first {...} block found anywhere."""
    stripped = text.strip()
    yield stripped

    if stripped.startswith("```"):
        fenced = stripped.strip("`")
        if fenced.lower().startswith("json"):
            fenced = fenced[4:]
        yield fenced.strip()

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        yield match.group(0)


def validate_or_repair(text: str, schema: type[BaseModel]) -> BaseModel:
    """Validate `text` as JSON matching `schema`, trying safe-repair
    candidates in order. Raises AISchemaValidationError if none parse."""
    for candidate in _repair_candidates(text):
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        try:
            return schema.model_validate(data)
        except Exception:  # noqa: BLE001 - pydantic ValidationError + friends
            continue

    raise AISchemaValidationError(
        f"model output did not match {schema.__name__} after repair attempts"
    )
