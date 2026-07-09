"""Unit tests for the worker heartbeat mechanism (requirement #1):
record_heartbeat's ownership check and the periodic _heartbeat_loop.

The actual heartbeat-vs-fixed-timeout SQL filtering (stale vs. active jobs)
is proven against a real Postgres in test_worker_integration.py — FakeSession
doesn't evaluate WHERE clauses, so it can only exercise the Python-level
logic here.
"""
from __future__ import annotations

import asyncio
import uuid

from app.agents import worker as worker_module
from tests.fakes import FakeResult, FakeSession
from tests.test_agent_jobs_and_worker import _job


def test_record_heartbeat_updates_when_worker_owns_job():
    job = _job(status=worker_module.AgentJobStatus.processing, worker_id="worker-1")
    session = FakeSession(results=[FakeResult(scalar=job)])
    before = job.heartbeat_at

    updated = worker_module.record_heartbeat(session, job.id, "worker-1")

    assert updated is True
    assert job.heartbeat_at != before
    assert session.commits == 1


def test_record_heartbeat_returns_false_when_not_owned():
    # job was reclaimed / claimed by a different worker / no longer processing
    # -> the query (in real Postgres) returns no row, simulated here directly
    session = FakeSession(results=[FakeResult(scalar=None)])

    updated = worker_module.record_heartbeat(session, uuid.uuid4(), "worker-1")

    assert updated is False
    assert session.commits == 0


def test_heartbeat_loop_refreshes_on_each_tick():
    job = _job(status=worker_module.AgentJobStatus.processing, worker_id="worker-1")
    tick_count = 0

    def session_factory():
        nonlocal tick_count
        tick_count += 1
        return _NullContextSession(FakeSession(results=[FakeResult(scalar=job)]))

    async def run_a_few_ticks():
        task = asyncio.create_task(
            worker_module._heartbeat_loop(session_factory, job.id, "worker-1", interval_s=0.02)
        )
        await asyncio.sleep(0.07)  # ~3 ticks at 0.02s
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run_a_few_ticks())

    assert tick_count >= 2


def test_heartbeat_loop_survives_a_failed_tick(monkeypatch):
    """A heartbeat failure (e.g. transient DB error) must never crash the
    loop or the job — it just logs and tries again next interval."""
    calls = {"n": 0}

    def failing_session_factory():
        calls["n"] += 1
        raise RuntimeError("simulated DB hiccup")

    async def run_briefly():
        task = asyncio.create_task(
            worker_module._heartbeat_loop(failing_session_factory, uuid.uuid4(), "worker-1", interval_s=0.02)
        )
        await asyncio.sleep(0.07)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run_briefly())

    assert calls["n"] >= 2  # kept retrying despite every tick failing


class _NullContextSession:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *exc):
        return False
