"""EngineClient against an httpx.MockTransport — no real engine/LLM needed.

Covers the contract v1.1 behaviours: submit/poll, backoff to terminal,
15-min cap -> EngineTimeout, 409 idempotency, and error-body code mapping.
"""
import uuid
from datetime import datetime, timezone

import httpx
import pytest

from app.engine.client import EngineClient, EngineError, EngineTimeout, IdempotencyConflict
from app.engine.schemas import AnalysisRequest, DocumentIn
from app.models import JobStatus, SourceType

NOOP_SLEEP = lambda *_: None  # noqa: E731


def _request() -> AnalysisRequest:
    return AnalysisRequest(
        request_id=uuid.uuid4(),
        project_id="p1",
        company_id="c1",
        documents=[DocumentIn(type=SourceType.email, content="we did extra works")],
    )


def _created():
    return {
        "job_id": "ej-1",
        "status": "queued",
        "request_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "links": {"self": "/v1/analyses/ej-1"},
    }


def _running():
    return {"job_id": "ej-1", "status": "running", "progress": {"stage": "classify", "percent": 0.5}}


def _succeeded():
    return {
        "job_id": "ej-1",
        "status": "succeeded",
        "engine_version": "v1",
        "result": {"project_id": "p1", "engine_version": "v1", "variations": []},
    }


def _transport(get_sequence):
    """POST -> 202 created; successive GETs walk get_sequence (last repeats)."""
    state = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(202, json=_created())
        item = get_sequence[min(state["i"], len(get_sequence) - 1)]
        state["i"] += 1
        return httpx.Response(200, json=item)

    return httpx.MockTransport(handler)


def test_run_to_completion_success():
    client = EngineClient("http://engine", transport=_transport([_running(), _succeeded()]))
    poll = client.run_to_completion(_request(), sleep=NOOP_SLEEP)
    assert poll.status == JobStatus.succeeded
    assert poll.is_terminal
    assert poll.engine_version == "v1"


def test_run_to_completion_timeout():
    client = EngineClient("http://engine", transport=_transport([_running()]))
    with pytest.raises(EngineTimeout) as ei:
        client.run_to_completion(_request(), max_wait=0, sleep=NOOP_SLEEP)
    assert ei.value.code == "ENGINE_TIMEOUT"
    assert ei.value.retryable is True


def test_submit_idempotency_conflict():
    def handler(_request):
        return httpx.Response(409, json={"error": {"code": "IDEMPOTENCY_KEY_REUSE", "message": "dup"}})

    client = EngineClient("http://engine", transport=httpx.MockTransport(handler))
    with pytest.raises(IdempotencyConflict):
        client.submit(_request())


def test_submit_error_maps_code():
    def handler(_request):
        return httpx.Response(
            400,
            json={"error": {"code": "UNSUPPORTED_CONTRACT_VERSION", "message": "nope", "retryable": False}},
        )

    client = EngineClient("http://engine", transport=httpx.MockTransport(handler))
    with pytest.raises(EngineError) as ei:
        client.submit(_request())
    assert ei.value.code == "UNSUPPORTED_CONTRACT_VERSION"
    assert ei.value.retryable is False
