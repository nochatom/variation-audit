"""Unit tests for app/agents/errors.py's exception classification."""
from __future__ import annotations

import litellm
import pytest

from app.agents.errors import (
    AIAuthError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    AIRateLimitError,
    classify_exception,
)


def test_classifies_litellm_authentication_error():
    exc = litellm.AuthenticationError("bad key", llm_provider="nvidia_nim", model="x")
    classified = classify_exception(exc, provider="openai", model="x")
    assert isinstance(classified, AIAuthError)
    assert classified.code == "AI_AUTH_ERROR"
    assert classified.retryable is False


def test_classifies_raw_403_status_code_as_auth_error():
    class Fake403(Exception):
        status_code = 403

    classified = classify_exception(Fake403("forbidden"))
    assert isinstance(classified, AIAuthError)


def test_classifies_litellm_rate_limit_error():
    exc = litellm.RateLimitError("too many requests", llm_provider="nvidia_nim", model="x")
    classified = classify_exception(exc)
    assert isinstance(classified, AIRateLimitError)
    assert classified.code == "AI_RATE_LIMIT_ERROR"
    assert classified.retryable is True


def test_classifies_litellm_timeout():
    exc = litellm.Timeout("timed out", model="x", llm_provider="nvidia_nim")
    classified = classify_exception(exc)
    assert isinstance(classified, AIProviderTimeoutError)
    assert classified.code == "AI_PROVIDER_TIMEOUT"
    assert classified.retryable is True


def test_classifies_litellm_service_unavailable():
    exc = litellm.ServiceUnavailableError("down", llm_provider="nvidia_nim", model="x")
    classified = classify_exception(exc)
    assert isinstance(classified, AIProviderUnavailableError)
    assert classified.code == "AI_PROVIDER_UNAVAILABLE"
    assert classified.retryable is True


def test_unknown_exception_defaults_to_retryable_unavailable():
    classified = classify_exception(RuntimeError("something odd"))
    assert isinstance(classified, AIProviderUnavailableError)
    assert classified.retryable is True


@pytest.mark.parametrize("status_code", [500, 502, 503, 504])
def test_5xx_status_codes_map_to_unavailable(status_code):
    class FakeHttpError(Exception):
        pass

    exc = FakeHttpError("server error")
    exc.status_code = status_code
    classified = classify_exception(exc)
    assert isinstance(classified, AIProviderUnavailableError)
