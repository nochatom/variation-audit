"""Phase 4 Gate 2 tests: worker.py's LLM-call telemetry sink is best-effort.

If provider_health.record()/circuit_breaker.record_outcome() fail, agent
execution must continue unaffected, llm_calls must still be recorded, and
the failure must only be logged — never raised out of the sink.
"""
from __future__ import annotations

import uuid

from app.agents import worker as worker_module
from app.agents import circuit_breaker, provider_health
from tests.test_agent_jobs_and_worker import _job


class _RaisingSessionFactory:
    """A session_factory whose context manager raises on __enter__ —
    simulates a telemetry DB that's completely unreachable."""

    def __call__(self):
        return self

    def __enter__(self):
        raise ConnectionError("simulated telemetry DB outage")

    def __exit__(self, *exc):
        return False


class _WorkingSessionFactory:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    def __enter__(self):
        return self._session

    def __exit__(self, *exc):
        return False


class _FakeTelemetrySession:
    """Minimal session stand-in — just enough for provider_health.record()/
    circuit_breaker.record_outcome() to be monkeypatched around; the real
    SQL execution is not under test here (that's Phase 3's job)."""


SAMPLE_METRICS = {
    "provider": "nvidia_nim", "model": "openai/gpt-oss-120b",
    "success": False, "error_code": "AI_PROVIDER_UNAVAILABLE",
    "latency_ms": 500, "input_tokens": 10, "output_tokens": 0,
    "number_of_retries": 2, "fallback_used": False,
}


# --------------------------------------------------------------------------
# Gate 2: telemetry failure never breaks the call
# --------------------------------------------------------------------------
def test_telemetry_failure_does_not_raise_and_llm_calls_still_recorded():
    job = _job()
    llm_calls: list[dict] = []
    sink = worker_module._make_llm_call_sink(job, llm_calls, _RaisingSessionFactory())

    sink(SAMPLE_METRICS)  # must not raise

    assert llm_calls == [SAMPLE_METRICS]


def test_telemetry_failure_is_logged(caplog):
    import logging

    job = _job()
    llm_calls: list[dict] = []
    sink = worker_module._make_llm_call_sink(job, llm_calls, _RaisingSessionFactory())

    with caplog.at_level(logging.ERROR, logger="app.agents.worker"):
        sink(SAMPLE_METRICS)

    assert any("provider telemetry recording failed" in r.message for r in caplog.records)


def test_no_session_factory_skips_telemetry_but_still_records_llm_calls():
    """The plain 2-arg process_job() path (no session_factory) — telemetry
    must degrade to a no-op, not crash, and llm_calls still gets the entry."""
    job = _job()
    llm_calls: list[dict] = []
    sink = worker_module._make_llm_call_sink(job, llm_calls, None)

    sink(SAMPLE_METRICS)

    assert llm_calls == [SAMPLE_METRICS]


# --------------------------------------------------------------------------
# Gate 2 (positive path): when the DB works, both telemetry calls happen
# --------------------------------------------------------------------------
def test_successful_telemetry_calls_both_provider_health_and_circuit_breaker(monkeypatch):
    recorded = {}

    def fake_record(session, metrics):
        recorded["health"] = metrics

    def fake_record_outcome(session, provider, *, success, error_code):
        recorded["circuit"] = (provider, success, error_code)

    monkeypatch.setattr(provider_health, "record", fake_record)
    monkeypatch.setattr(circuit_breaker, "record_outcome", fake_record_outcome)

    job = _job()
    llm_calls: list[dict] = []
    session = _FakeTelemetrySession()
    sink = worker_module._make_llm_call_sink(job, llm_calls, _WorkingSessionFactory(session))

    sink(SAMPLE_METRICS)

    assert recorded["health"] == SAMPLE_METRICS
    assert recorded["circuit"] == ("nvidia_nim", False, "AI_PROVIDER_UNAVAILABLE")
    assert llm_calls == [SAMPLE_METRICS]


def test_provider_health_failure_does_not_prevent_llm_calls_recording(monkeypatch):
    """Even a partial telemetry failure (health write fails, circuit update
    never runs as a result) must never affect llm_calls or raise."""
    def failing_record(session, metrics):
        raise RuntimeError("simulated provider_health.record failure")

    monkeypatch.setattr(provider_health, "record", failing_record)

    job = _job()
    llm_calls: list[dict] = []
    session = _FakeTelemetrySession()
    sink = worker_module._make_llm_call_sink(job, llm_calls, _WorkingSessionFactory(session))

    sink(SAMPLE_METRICS)  # must not raise

    assert llm_calls == [SAMPLE_METRICS]


# --------------------------------------------------------------------------
# Gate 2: a telemetry failure must not affect the job's own success/failure
# --------------------------------------------------------------------------
def test_process_job_succeeds_even_when_telemetry_sink_would_fail(monkeypatch):
    from app.models import AgentAnalysisJob, AgentJobStatus
    from tests.fakes import FakeSession

    job = _job(status=AgentJobStatus.processing)
    session = FakeSession()

    async def fake_analyze(session_, project_id, **kwargs):
        # simulate an LLM call whose metrics sink talks to a dead telemetry DB
        kwargs["on_llm_call"](SAMPLE_METRICS)
        kwargs["on_agent_complete"]("report_generation_agent", 95)
        return {"project_id": str(job.project_id)}

    monkeypatch.setattr(worker_module, "analyze_project_with_agents", fake_analyze)

    worker_module.process_job(session, job, "worker-1", session_factory=_RaisingSessionFactory())

    assert job.status == AgentJobStatus.completed
    assert job.llm_calls == [SAMPLE_METRICS]
