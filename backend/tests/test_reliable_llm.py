"""Unit tests for app/agents/reliable_llm.py's retry/fallback behavior.

Uses a fake transport (duck-typed like LiteLlm: a `.model` attr and an
async `generate_content_async(llm_request, stream)` generator) so these
tests never touch the network — only the retry/classification/fallback
logic in ReliableLlm itself is under test.
"""
from __future__ import annotations

import asyncio

import litellm
import pytest
from google.adk.models.llm_response import LlmResponse

from app.agents.reliable_llm import ReliableLlm


class FakeTransport:
    """`plan` is a list of Exception instances or LlmResponse instances,
    consumed one per call; once exhausted, repeats the last entry."""

    def __init__(self, model: str, plan: list):
        self.model = model
        self._plan = list(plan)
        self.calls = 0

    async def generate_content_async(self, llm_request, stream: bool = False):
        index = min(self.calls, len(self._plan) - 1)
        item = self._plan[index]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        yield item


def _run(coro):
    return asyncio.run(coro)


async def _collect(reliable: ReliableLlm, llm_request=None):
    return [r async for r in reliable.generate_content_async(llm_request)]


def _unavailable():
    return litellm.ServiceUnavailableError("down", llm_provider="nvidia_nim", model="x")


def _auth_error():
    return litellm.AuthenticationError("bad key", llm_provider="nvidia_nim", model="x")


def test_succeeds_on_first_attempt_no_retry_no_fallback():
    ok = LlmResponse()
    primary = FakeTransport("primary", [ok])
    fallback = FakeTransport("fallback", [ok])
    reliable = ReliableLlm(primary=primary, primary_provider="gemini",
                           fallback=fallback, fallback_provider="openai",
                           max_retries=2, base_backoff_s=0)

    responses = _run(_collect(reliable))

    assert responses == [ok]
    assert primary.calls == 1
    assert fallback.calls == 0


def test_transient_error_retried_then_succeeds_on_primary():
    ok = LlmResponse()
    primary = FakeTransport("primary", [_unavailable(), ok])
    reliable = ReliableLlm(primary=primary, primary_provider="gemini",
                           fallback=None, fallback_provider=None,
                           max_retries=2, base_backoff_s=0)

    responses = _run(_collect(reliable))

    assert responses == [ok]
    assert primary.calls == 2


def test_primary_exhausts_retries_then_falls_back():
    ok = LlmResponse()
    primary = FakeTransport("primary", [_unavailable(), _unavailable(), _unavailable()])
    fallback = FakeTransport("fallback", [ok])
    reliable = ReliableLlm(primary=primary, primary_provider="gemini",
                           fallback=fallback, fallback_provider="openai",
                           max_retries=2, base_backoff_s=0)

    responses = _run(_collect(reliable))

    assert responses == [ok]
    assert primary.calls == 3  # 1 initial + 2 retries
    assert fallback.calls == 1


def test_auth_error_raises_immediately_no_retry_no_fallback():
    primary = FakeTransport("primary", [_auth_error()])
    fallback = FakeTransport("fallback", [LlmResponse()])
    reliable = ReliableLlm(primary=primary, primary_provider="gemini",
                           fallback=fallback, fallback_provider="openai",
                           max_retries=2, base_backoff_s=0)

    with pytest.raises(Exception) as excinfo:
        _run(_collect(reliable))

    assert excinfo.value.__class__.__name__ == "AIAuthError"
    assert primary.calls == 1
    assert fallback.calls == 0


def test_no_fallback_configured_raises_after_exhausting_retries():
    primary = FakeTransport("primary", [_unavailable(), _unavailable(), _unavailable()])
    reliable = ReliableLlm(primary=primary, primary_provider="gemini",
                           fallback=None, fallback_provider=None,
                           max_retries=2, base_backoff_s=0)

    with pytest.raises(Exception) as excinfo:
        _run(_collect(reliable))

    assert excinfo.value.__class__.__name__ == "AIProviderUnavailableError"
    assert primary.calls == 3


def test_fallback_also_failing_raises_fallbacks_error():
    primary = FakeTransport("primary", [_unavailable()] * 3)
    fallback = FakeTransport("fallback", [_unavailable()] * 3)
    reliable = ReliableLlm(primary=primary, primary_provider="gemini",
                           fallback=fallback, fallback_provider="openai",
                           max_retries=2, base_backoff_s=0)

    with pytest.raises(Exception) as excinfo:
        _run(_collect(reliable))

    assert excinfo.value.__class__.__name__ == "AIProviderUnavailableError"
    assert primary.calls == 3
    assert fallback.calls == 3
