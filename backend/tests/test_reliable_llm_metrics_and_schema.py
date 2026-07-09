"""Unit tests for ReliableLlm's LLM-metrics collection (requirement #3) and
output-schema enforcement across primary/fallback (requirement #4).
"""
from __future__ import annotations

import asyncio

from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import BaseModel

from app.agents.context import current_agent_name, current_job_id, current_llm_call_sink
from app.agents.reliable_llm import ReliableLlm
from tests.test_reliable_llm import FakeTransport


class VariationOut(BaseModel):
    variation_found: bool
    confidence: float


VALID = '{"variation_found": true, "confidence": 0.9}'
INVALID = "not json at all, sorry"


def _response(text: str, usage=None) -> LlmResponse:
    part = types.Part(text=text)
    content = types.Content(role="model", parts=[part])
    return LlmResponse(content=content, usage_metadata=usage)


def _run(coro):
    return asyncio.run(coro)


async def _collect(reliable, llm_request):
    return [r async for r in reliable.generate_content_async(llm_request)]


def _schema_request():
    return LlmRequest(model="x", config=types.GenerateContentConfig(response_schema=VariationOut))


# --------------------------------------------------------------------------
# Metrics collection
# --------------------------------------------------------------------------
def test_metrics_sink_receives_one_record_per_call():
    usage = types.GenerateContentResponseUsageMetadata(prompt_token_count=42, candidates_token_count=7)
    ok = _response(VALID, usage=usage)
    primary = FakeTransport("primary", [ok])
    reliable = ReliableLlm(primary=primary, primary_provider="gemini", max_retries=2, base_backoff_s=0)

    collected = []
    job_token = current_job_id.set("job-123")
    agent_token = current_agent_name.set("variation_detection_agent")
    sink_token = current_llm_call_sink.set(collected.append)
    try:
        _run(_collect(reliable, _schema_request()))
    finally:
        current_job_id.reset(job_token)
        current_agent_name.reset(agent_token)
        current_llm_call_sink.reset(sink_token)

    assert len(collected) == 1
    metrics = collected[0]
    assert metrics["job_id"] == "job-123"
    assert metrics["agent"] == "variation_detection_agent"
    assert metrics["provider"] == "gemini"
    assert metrics["input_tokens"] == 42
    assert metrics["output_tokens"] == 7
    assert metrics["number_of_retries"] == 0
    assert metrics["fallback_used"] is False
    assert isinstance(metrics["latency_ms"], (int, float))


def test_metrics_record_never_contains_prompt_or_response_text():
    ok = _response(VALID)
    primary = FakeTransport("primary", [ok])
    reliable = ReliableLlm(primary=primary, primary_provider="gemini", max_retries=2, base_backoff_s=0)

    collected = []
    token = current_llm_call_sink.set(collected.append)
    try:
        _run(_collect(reliable, _schema_request()))
    finally:
        current_llm_call_sink.reset(token)

    serialized = str(collected[0])
    assert VALID not in serialized
    assert "variation_found" not in serialized


def test_metrics_reflect_fallback_and_retries():
    from app.agents.errors import AIProviderError

    class Unavailable(Exception):
        pass

    def _err():
        import litellm
        return litellm.ServiceUnavailableError("down", llm_provider="nvidia_nim", model="x")

    primary = FakeTransport("primary", [_err(), _err(), _err()])
    fallback = FakeTransport("fallback", [_response(VALID)])
    reliable = ReliableLlm(primary=primary, primary_provider="gemini",
                           fallback=fallback, fallback_provider="openai",
                           max_retries=2, base_backoff_s=0)

    collected = []
    token = current_llm_call_sink.set(collected.append)
    try:
        _run(_collect(reliable, _schema_request()))
    finally:
        current_llm_call_sink.reset(token)

    metrics = collected[0]
    assert metrics["fallback_used"] is True
    assert metrics["provider"] == "openai"
    assert metrics["number_of_retries"] >= 2


# --------------------------------------------------------------------------
# Schema validation across primary/fallback
# --------------------------------------------------------------------------
def test_valid_schema_output_passes_through():
    ok = _response(VALID)
    primary = FakeTransport("primary", [ok])
    reliable = ReliableLlm(primary=primary, primary_provider="gemini", max_retries=2, base_backoff_s=0)

    responses = _run(_collect(reliable, _schema_request()))

    assert responses == [ok]


def test_malformed_output_triggers_retry_then_succeeds():
    bad = _response(INVALID)
    good = _response(VALID)
    primary = FakeTransport("primary", [bad, good])
    reliable = ReliableLlm(primary=primary, primary_provider="gemini", max_retries=2, base_backoff_s=0)

    responses = _run(_collect(reliable, _schema_request()))

    assert responses == [good]
    assert primary.calls == 2


def test_primary_always_malformed_falls_back_to_schema_conforming_model():
    bad = _response(INVALID)
    good = _response(VALID)
    primary = FakeTransport("primary", [bad, bad, bad])
    fallback = FakeTransport("fallback", [good])
    reliable = ReliableLlm(primary=primary, primary_provider="gemini",
                           fallback=fallback, fallback_provider="openai",
                           max_retries=2, base_backoff_s=0)

    responses = _run(_collect(reliable, _schema_request()))

    assert responses == [good]
    assert fallback.calls == 1


def test_fallback_also_malformed_raises_schema_error():
    from app.agents.errors import AISchemaValidationError
    import pytest

    bad = _response(INVALID)
    primary = FakeTransport("primary", [bad] * 3)
    fallback = FakeTransport("fallback", [bad] * 3)
    reliable = ReliableLlm(primary=primary, primary_provider="gemini",
                           fallback=fallback, fallback_provider="openai",
                           max_retries=2, base_backoff_s=0)

    with pytest.raises(AISchemaValidationError):
        _run(_collect(reliable, _schema_request()))


def test_no_schema_configured_skips_validation_entirely():
    # response text doesn't matter -> no output_schema on the request means
    # ReliableLlm shouldn't even attempt to parse it as JSON.
    weird = _response("plain prose, not JSON, and that's fine here")
    primary = FakeTransport("primary", [weird])
    reliable = ReliableLlm(primary=primary, primary_provider="gemini", max_retries=2, base_backoff_s=0)

    plain_request = LlmRequest(model="x", config=types.GenerateContentConfig())
    responses = _run(_collect(reliable, plain_request))

    assert responses == [weird]
