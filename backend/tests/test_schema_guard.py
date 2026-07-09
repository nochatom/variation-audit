"""Unit tests for app/agents/schema_guard.py — the primary/fallback output
contract enforcement (requirement #4)."""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.agents.errors import AISchemaValidationError
from app.agents.schema_guard import extract_text, validate_or_repair


class VariationOut(BaseModel):
    variation_found: bool
    clause_reference: str
    evidence: list[str]
    confidence: float


VALID_JSON = '{"variation_found": true, "clause_reference": "12.3", "evidence": ["a"], "confidence": 0.8}'


def test_valid_json_validates_directly():
    result = validate_or_repair(VALID_JSON, VariationOut)
    assert result.variation_found is True
    assert result.clause_reference == "12.3"


def test_markdown_fenced_json_is_repaired():
    fenced = f"```json\n{VALID_JSON}\n```"
    result = validate_or_repair(fenced, VariationOut)
    assert result.confidence == 0.8


def test_json_embedded_in_prose_is_repaired():
    prose = f"Sure, here is the result:\n{VALID_JSON}\nLet me know if you need anything else."
    result = validate_or_repair(prose, VariationOut)
    assert result.evidence == ["a"]


def test_invalid_json_raises_schema_validation_error():
    with pytest.raises(AISchemaValidationError):
        validate_or_repair("{not valid json at all", VariationOut)


def test_missing_required_fields_raises_schema_validation_error():
    incomplete = '{"variation_found": true}'
    with pytest.raises(AISchemaValidationError):
        validate_or_repair(incomplete, VariationOut)


def test_fallback_model_producing_same_contract_shape_validates_identically():
    # Simulates the fallback model (openai/gpt-oss-120b) returning the same
    # logical content in a different textual wrapper than the primary
    # (google/gemma-4-31b-it) would have — both must validate identically.
    primary_style = VALID_JSON
    fallback_style = f"```json\n{VALID_JSON}\n```"

    primary_result = validate_or_repair(primary_style, VariationOut)
    fallback_result = validate_or_repair(fallback_style, VariationOut)

    assert primary_result == fallback_result


class _FakePart:
    def __init__(self, text):
        self.text = text


class _FakeContent:
    def __init__(self, parts):
        self.parts = parts


class _FakeResponse:
    def __init__(self, content=None):
        self.content = content


def test_extract_text_concatenates_parts():
    response = _FakeResponse(content=_FakeContent([_FakePart("hello "), _FakePart("world")]))
    assert extract_text(response) == "hello world"


def test_extract_text_returns_none_when_no_content():
    assert extract_text(_FakeResponse(content=None)) is None
    assert extract_text(_FakeResponse(content=_FakeContent([]))) is None
