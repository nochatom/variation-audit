"""Regression tests for the failure-path metrics gap fix (Phase 3.5):
_emit_metrics()/CallOutcome must fire exactly once per logical call on
every outcome — success, primary failure with no fallback, retry
exhaustion with no fallback, and fallback-also-fails — never zero times,
never twice.
"""
from __future__ import annotations

import asyncio

import litellm
import pytest
from google.adk.models.llm_response import LlmResponse

from app.agents.context import current_llm_call_sink
from app.agents.errors import AIAuthError, AIProviderUnavailableError
from app.agents.reliable_llm import ReliableLlm
from tests.test_reliable_llm import FakeTransport


def _run(coro):
    return asyncio.run(coro)


async def _collect(reliable: ReliableLlm, llm_request=None):
    return [r async for r in reliable.generate_content_async(llm_request)]


def _run_with_sink(reliable: ReliableLlm):
    """Runs generate_content_async fully (catching any raised exception)
    with a sink installed, returning (records, raised_exception_or_None)."""
    records: list[dict] = []
    token = current_llm_call_sink.set(records.append)
    try:
        try:
            responses = _run(_collect(reliable))
            return records, responses, None
        except Exception as exc:  # noqa: BLE001 - captured for assertions, not swallowed silently
            return records, None, exc
    finally:
        current_llm_call_sink.reset(token)


def _unavailable():
    return litellm.ServiceUnavailableError("down", llm_provider="nvidia_nim", model="x")


def _auth_error():
    return litellm.AuthenticationError("bad key", llm_provider="nvidia_nim", model="x")


# --------------------------------------------------------------------------
# Successful fallback — exactly one record, success=True
# --------------------------------------------------------------------------
def test_successful_fallback_emits_exactly_one_success_record():
    ok = LlmResponse()
    primary = FakeTransport("primary", [_unavailable(), _unavailable(), _unavailable()])
    fallback = FakeTransport("fallback", [ok])
    reliable = ReliableLlm(primary=primary, primary_provider="gemini",
                           fallback=fallback, fallback_provider="openai",
                           max_retries=2, base_backoff_s=0)

    records, responses, exc = _run_with_sink(reliable)

    assert exc is None
    assert responses == [ok]
    assert len(records) == 1
    assert records[0]["success"] is True
    assert records[0]["error_code"] is None
    assert records[0]["fallback_used"] is True
    assert records[0]["provider"] == "openai"


# --------------------------------------------------------------------------
# Primary failure, no fallback configured — exactly one record, success=False
# --------------------------------------------------------------------------
def test_primary_failure_without_fallback_emits_exactly_one_failure_record():
    primary = FakeTransport("primary", [_auth_error()])
    reliable = ReliableLlm(primary=primary, primary_provider="gemini",
                           fallback=None, fallback_provider=None,
                           max_retries=2, base_backoff_s=0)

    records, responses, exc = _run_with_sink(reliable)

    assert responses is None
    assert exc is not None and exc.__class__.__name__ == "AIAuthError"
    assert len(records) == 1
    assert records[0]["success"] is False
    assert records[0]["error_code"] == "AI_AUTH_ERROR"
    assert records[0]["fallback_used"] is False
    assert primary.calls == 1  # auth errors are not retried


# --------------------------------------------------------------------------
# Retry exhaustion, no fallback configured — exactly one record, success=False
# --------------------------------------------------------------------------
def test_retry_exhaustion_without_fallback_emits_exactly_one_failure_record():
    primary = FakeTransport("primary", [_unavailable(), _unavailable(), _unavailable()])
    reliable = ReliableLlm(primary=primary, primary_provider="gemini",
                           fallback=None, fallback_provider=None,
                           max_retries=2, base_backoff_s=0)

    records, responses, exc = _run_with_sink(reliable)

    assert responses is None
    assert exc is not None and exc.__class__.__name__ == "AIProviderUnavailableError"
    assert len(records) == 1
    assert records[0]["success"] is False
    assert records[0]["error_code"] == "AI_PROVIDER_UNAVAILABLE"
    assert records[0]["fallback_used"] is False
    assert records[0]["number_of_retries"] == 2  # 1 initial + 2 retries = 3 attempts -> 2 retries
    assert primary.calls == 3


# --------------------------------------------------------------------------
# Fallback also fails — exactly one record, attributed to the fallback
# --------------------------------------------------------------------------
def test_fallback_failure_emits_exactly_one_failure_record():
    primary = FakeTransport("primary", [_unavailable()] * 3)
    fallback = FakeTransport("fallback", [_unavailable()] * 3)
    reliable = ReliableLlm(primary=primary, primary_provider="gemini",
                           fallback=fallback, fallback_provider="openai",
                           max_retries=2, base_backoff_s=0)

    records, responses, exc = _run_with_sink(reliable)

    assert responses is None
    assert exc is not None and exc.__class__.__name__ == "AIProviderUnavailableError"
    assert len(records) == 1
    assert records[0]["success"] is False
    assert records[0]["error_code"] == "AI_PROVIDER_UNAVAILABLE"
    assert records[0]["fallback_used"] is True
    assert records[0]["provider"] == "openai"  # attributed to the terminal (fallback) attempt
    assert primary.calls == 3
    assert fallback.calls == 3


# --------------------------------------------------------------------------
# Baseline: plain success (no fallback needed) — exactly one record
# --------------------------------------------------------------------------
def test_plain_success_emits_exactly_one_success_record():
    ok = LlmResponse()
    primary = FakeTransport("primary", [ok])
    reliable = ReliableLlm(primary=primary, primary_provider="gemini",
                           max_retries=2, base_backoff_s=0)

    records, responses, exc = _run_with_sink(reliable)

    assert exc is None
    assert responses == [ok]
    assert len(records) == 1
    assert records[0]["success"] is True
    assert records[0]["fallback_used"] is False
