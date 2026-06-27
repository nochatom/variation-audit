"""Tests for the engine ingest+baseline normalization stage.

No live LLM: a fake Anthropic-shaped client returns canned structured JSON.
"""
import json

from app.ai.normalization.dates import normalize_date
from app.ai.normalization.parser import (
    MODEL,
    _build_user_prompt,
    _output_format,
    parse_document,
)
from app.ai.normalization.schema import NormalizedDocument, ScopeAction, SourceType


# -- fake Anthropic client -------------------------------------------------
class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Response:
    def __init__(self, text):
        self.content = [_Block(text)]


class FakeMessages:
    def __init__(self, payload: dict):
        self._payload = payload
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return _Response(json.dumps(self._payload))


class FakeClient:
    def __init__(self, payload: dict):
        self.messages = FakeMessages(payload)


# -- date normalization ----------------------------------------------------
def test_normalize_date_day_first():
    assert normalize_date("05/03/2026") == "2026-03-05"   # 5 March, not 3 May
    assert normalize_date("5 March 2026") == "2026-03-05"
    assert normalize_date("2026-03-05") == "2026-03-05"


def test_normalize_date_unparseable_is_none():
    assert normalize_date("sometime next week") is None
    assert normalize_date(None) is None
    assert normalize_date("") is None


# -- output format schema --------------------------------------------------
def test_output_format_is_strict_json_schema():
    fmt = _output_format()
    assert fmt["type"] == "json_schema"
    # extra="forbid" -> additionalProperties false (required by structured outputs)
    assert fmt["schema"]["additionalProperties"] is False


def test_build_user_prompt_includes_metadata_and_content():
    prompt = _build_user_prompt("d1", "rfi", "thread#3", "2026-03-05", "please advise")
    assert "document_id: d1" in prompt
    assert "source_type: rfi" in prompt
    assert "please advise" in prompt


# -- parse_document --------------------------------------------------------
def _payload():
    return {
        "document_id": "d1",
        "source_type": "site_instruction",
        "summary": "Superintendent instructed additional excavation.",
        "event_date": "05/03/2026",                       # day-first -> normalized
        "trade": "civil",
        "parties": [{"name": "J. Smith", "role": "superintendent"}],
        "references": [{"ref_type": "rfi", "value": "RFI-012"}],
        "scope_items": [
            {
                "description": "Additional 20m3 rock excavation not in contract",
                "action": "instructed",
                "potential_variation": True,
                "mentioned_date": "5 March 2026",
            }
        ],
    }


def test_parse_document_returns_normalized_and_uses_opus():
    client = FakeClient(_payload())
    doc = parse_document(
        client, document_id="d1", source_type="site_instruction",
        content="Please proceed with the extra rock excavation.",
    )
    assert isinstance(doc, NormalizedDocument)
    assert doc.source_type == SourceType.site_instruction
    assert doc.trade == "civil"
    assert len(doc.scope_items) == 1
    assert doc.scope_items[0].action == ScopeAction.instructed
    assert doc.scope_items[0].potential_variation is True
    # deterministic post-normalization applied day-first
    assert doc.event_date == "2026-03-05"
    assert doc.scope_items[0].mentioned_date == "2026-03-05"
    # correct model + adaptive thinking + structured outputs were requested
    kw = client.messages.last_kwargs
    assert kw["model"] == MODEL == "claude-opus-4-8"
    assert kw["thinking"] == {"type": "adaptive"}
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert "temperature" not in kw and "top_p" not in kw   # removed on Opus 4.8
