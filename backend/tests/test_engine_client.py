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
        contract_text="The contractor shall install the switchboard.",
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


def test_run_to_completion_cancels_when_signalled():
    # cancel_check returning True must abort the poll loop with EngineCancelled
    # so the worker can mark the job cancelled instead of failed.
    from app.engine.client import EngineCancelled

    client = EngineClient("http://engine", transport=_transport([_running(), _running()]))
    with pytest.raises(EngineCancelled) as ei:
        client.run_to_completion(_request(), sleep=NOOP_SLEEP, cancel_check=lambda: True)
    assert ei.value.code == "CANCELLED"
    assert ei.value.retryable is False


def test_run_to_completion_not_cancelled_when_signal_false():
    client = EngineClient("http://engine", transport=_transport([_running(), _succeeded()]))
    poll = client.run_to_completion(_request(), sleep=NOOP_SLEEP, cancel_check=lambda: False)
    assert poll.status == JobStatus.succeeded


def test_run_to_completion_heartbeat_fires_per_nonterminal_poll():
    # on_poll (the worker's progress heartbeat) must fire once per non-terminal
    # poll and NOT on the terminal one — so a long AI Analysis stage keeps the
    # live stream ticking instead of falsely reporting a stall.
    calls = []
    client = EngineClient("http://engine", transport=_transport([_running(), _running(), _succeeded()]))
    poll = client.run_to_completion(_request(), sleep=NOOP_SLEEP, on_poll=lambda: calls.append(1))
    assert poll.status == JobStatus.succeeded
    assert len(calls) == 2


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


def _flaky_transport(fail_gets: int):
    """POST -> 202; the first `fail_gets` GETs raise RemoteProtocolError
    ("Server disconnected..."), i.e. the stale keep-alive reuse race; then GET
    -> succeeded. Reproduces the exact root cause of the intermittent failure."""
    state = {"gets": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(202, json=_created())
        state["gets"] += 1
        if state["gets"] <= fail_gets:
            raise httpx.RemoteProtocolError(
                "Server disconnected without sending a response.", request=request
            )
        return httpx.Response(200, json=_succeeded())

    return httpx.MockTransport(handler)


def test_poll_retries_transient_disconnect():
    # One stale-connection disconnect, then success — the single retry recovers
    # on a fresh connection instead of failing the whole job (root-cause fix).
    client = EngineClient("http://engine", transport=_flaky_transport(fail_gets=1))
    poll = client.run_to_completion(_request(), sleep=NOOP_SLEEP)
    assert poll.status == JobStatus.succeeded


def test_poll_gives_up_after_retry_exhausted():
    # Persistent disconnect (not the transient race): surface a clean,
    # retryable ENGINE_UNAVAILABLE rather than a raw httpx exception.
    client = EngineClient("http://engine", transport=_flaky_transport(fail_gets=99))
    with pytest.raises(EngineError) as ei:
        client.run_to_completion(_request(), sleep=NOOP_SLEEP)
    assert ei.value.code == "ENGINE_UNAVAILABLE"
    assert ei.value.retryable is True
