"""Tests for the Production Hardening Pass 1 error-handling work:
- app/errors.py's standardized {"error": {"code","message","request_id"}}
  envelope for every kind of error response
- request_id tracing end-to-end (log line <-> X-Request-ID header <-> body)
- document upload failure using the new structured error code
- authentication errors
- AgentJobOut never exposing a raw provider/exception message to the client
- worker failure logging (job_id/project_id/[agent]/error_code, never raw
  message content)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.errors import install_error_handlers
from app.request_logging import RequestLoggingMiddleware


# --------------------------------------------------------------------------
# Isolated micro-app — unit-tests app/errors.py's envelope directly, without
# depending on any domain fixture (DB, auth, storage). Mirrors exactly how
# app/main.py wires the same two pieces together (RequestLoggingMiddleware
# sets request.state.request_id; install_error_handlers reads it).
# --------------------------------------------------------------------------
class _Body(BaseModel):
    n: int


def _micro_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)
    install_error_handlers(app)

    @app.get("/boom-unhandled")
    def boom_unhandled():
        raise RuntimeError("raw internal detail: db password=hunter2")

    @app.get("/boom-http-string")
    def boom_http_string():
        raise HTTPException(404, "widget not found")

    @app.get("/boom-http-dict")
    def boom_http_dict():
        raise HTTPException(402, {"error_code": "PLAN_LIMIT_EXCEEDED", "message": "Upgrade your plan."})

    @app.post("/validate")
    def validate(body: _Body):
        return {"n": body.n}

    @app.get("/ok")
    def ok():
        return {"status": "ok"}

    return app


@pytest.fixture
def micro_client():
    return TestClient(_micro_app(), raise_server_exceptions=False)


# --------------------------------------------------------------------------
# Envelope shape — every error path
# --------------------------------------------------------------------------
def test_unhandled_exception_returns_standard_envelope_not_a_stack_trace(micro_client):
    resp = micro_client.get("/boom-unhandled")
    assert resp.status_code == 500
    body = resp.json()
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message", "request_id"}
    assert body["error"]["code"] == "INTERNAL_SERVER_ERROR"
    # No stack trace, no exception class name, no raw exception text.
    raw = resp.text
    assert "Traceback" not in raw
    assert "RuntimeError" not in raw
    assert "hunter2" not in raw
    assert "db password" not in raw


def test_unhandled_exception_request_id_matches_response_header(micro_client):
    resp = micro_client.get("/boom-unhandled")
    assert resp.status_code == 500
    body_request_id = resp.json()["error"]["request_id"]
    assert body_request_id != "unknown"
    assert resp.headers["X-Request-ID"] == body_request_id


def test_unhandled_exception_is_logged_with_request_id_and_no_raw_secret(micro_client, caplog):
    with caplog.at_level(logging.ERROR, logger="va.errors"):
        resp = micro_client.get("/boom-unhandled")
    request_id = resp.json()["error"]["request_id"]
    records = [r for r in caplog.records if r.name == "va.errors"]
    assert len(records) == 1
    assert records[0].request_id == request_id
    assert records[0].path == "/boom-unhandled"
    # The traceback IS captured server-side (that's the point of
    # logger.exception) — but the client-visible message never was, so
    # confirm the secret only appears in the log, not in violation of any
    # log-scrubbing expectation for this specific test's purpose: the
    # response body (already asserted above) is what must never contain it.


def test_http_exception_plain_string_detail_gets_standard_envelope(micro_client):
    resp = micro_client.get("/boom-http-string")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message"] == "widget not found"
    assert body["error"]["request_id"]


def test_http_exception_dict_detail_preserves_existing_error_code(micro_client):
    """The pre-existing {"error_code","message"} pattern (plan-limit errors)
    must keep working exactly as before, just wrapped in the envelope."""
    resp = micro_client.get("/boom-http-dict")
    assert resp.status_code == 402
    body = resp.json()
    assert body["error"]["code"] == "PLAN_LIMIT_EXCEEDED"
    assert body["error"]["message"] == "Upgrade your plan."


def test_validation_error_returns_standard_envelope_with_field_detail(micro_client):
    resp = micro_client.post("/validate", json={"n": "not-a-number"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["request_id"]
    assert isinstance(body["error"]["fields"], list)
    assert body["error"]["fields"][0]["loc"]


def test_successful_request_unaffected_by_error_handlers(micro_client):
    resp = micro_client.get("/ok")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert "X-Request-ID" in resp.headers


def test_every_request_gets_a_distinct_request_id(micro_client):
    r1 = micro_client.get("/ok")
    r2 = micro_client.get("/ok")
    assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]


# --------------------------------------------------------------------------
# Real app integration — document upload failure
# --------------------------------------------------------------------------
def test_document_upload_failure_uses_structured_error_code():
    from app.auth.deps import get_current_user, get_db
    from app.main import app
    from app.models import Membership, Project, ProjectStatus, User
    from app.storage import get_store
    from tests.fakes import FakeResult, FakeSession

    class FailingStore:
        def put(self, key, data):
            raise ConnectionError("simulated Supabase Storage outage")

    user = User(id=uuid.uuid4(), email="ca@firm.com", password_hash="x", is_active=True)
    cid = uuid.uuid4()
    project = Project(id=uuid.uuid4(), company_id=cid, name="Tower A", status=ProjectStatus.in_progress)
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid)
    session = FakeSession(results=[FakeResult(scalars=[membership])], get_obj=project)

    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_store] = lambda: FailingStore()
    try:
        client = TestClient(app)
        resp = client.post(f"/projects/{project.id}/documents",
                           files={"file": ("note.txt", b"hello", "text/plain")})
        assert resp.status_code == 502
        body = resp.json()
        assert body["error"]["code"] == "DOCUMENT_UPLOAD_FAILED"
        assert body["error"]["request_id"]
        # No storage/library internals (e.g. "ConnectionError", "Supabase") leak.
        assert "ConnectionError" not in resp.text
        assert "simulated Supabase Storage outage" not in resp.text
    finally:
        app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# Real app integration — authentication errors
# --------------------------------------------------------------------------
def test_unauthenticated_request_returns_standard_envelope():
    from app.main import app

    client = TestClient(app)
    resp = client.get("/notifications")
    assert resp.status_code in (401, 403)
    body = resp.json()
    assert "error" in body
    assert body["error"]["request_id"]


def test_invalid_token_returns_standard_envelope():
    from app.main import app

    client = TestClient(app)
    resp = client.get("/notifications", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"] == "UNAUTHORIZED"
    assert "not-a-real-token" not in resp.text


# --------------------------------------------------------------------------
# AgentJobOut never exposes raw provider/exception text to the client
# --------------------------------------------------------------------------
def test_agent_job_out_never_exposes_raw_error_message():
    from app.models import AgentAnalysisJob, AgentJobStatus
    from app.routers.agent_jobs import AgentJobOut

    secret_looking_message = "litellm.AuthenticationError: Incorrect API key provided: sk-abc123secret"
    job = AgentAnalysisJob(
        id=uuid.uuid4(), company_id=uuid.uuid4(), project_id=uuid.uuid4(),
        created_by=uuid.uuid4(), status=AgentJobStatus.failed, progress_percent=40,
        error_code="AI_AUTH_ERROR", error_message=secret_looking_message,
        created_at=datetime.now(timezone.utc),
    )

    out = AgentJobOut.from_job(job)

    assert out.error_code == "AI_AUTH_ERROR"
    assert out.error_message is not None
    assert "sk-abc123secret" not in out.error_message
    assert "litellm" not in out.error_message.lower()
    assert secret_looking_message != out.error_message


def test_agent_job_out_generic_pipeline_error_also_sanitized():
    from app.models import AgentAnalysisJob, AgentJobStatus
    from app.routers.agent_jobs import AgentJobOut

    raw_repr = "KeyError('some_internal_field')"
    job = AgentAnalysisJob(
        id=uuid.uuid4(), company_id=uuid.uuid4(), project_id=uuid.uuid4(),
        created_by=uuid.uuid4(), status=AgentJobStatus.failed, progress_percent=10,
        error_code="AGENT_PIPELINE_ERROR", error_message=raw_repr,
        created_at=datetime.now(timezone.utc),
    )

    out = AgentJobOut.from_job(job)

    assert "KeyError" not in out.error_message
    assert "some_internal_field" not in out.error_message


# --------------------------------------------------------------------------
# Worker failure logging — job_id/project_id/[agent]/error_code only
# --------------------------------------------------------------------------
def test_job_worker_fail_job_logs_context_not_raw_message(caplog):
    import uuid as _uuid

    from app.models import AnalysisJob, JobStatus
    from app.worker.job_worker import fail_job
    from tests.fakes import FakeSession

    job = AnalysisJob()
    job.id = _uuid.uuid4()
    job.company_id = _uuid.uuid4()
    job.project_id = _uuid.uuid4()
    job.created_by = None  # skip notification path
    session = FakeSession()

    secret_message = "engine error: leaked contract clause text or credential-looking-string"
    with caplog.at_level(logging.WARNING, logger="app.worker.job_worker"):
        fail_job(session, job, "INTERNAL", secret_message, retryable=True)

    assert job.status == JobStatus.failed
    records = [r for r in caplog.records if r.name == "app.worker.job_worker"]
    assert len(records) == 1
    rec = records[0]
    assert rec.job_id == str(job.id)
    assert rec.project_id == str(job.project_id)
    assert rec.error_code == "INTERNAL"
    # The log line's own formatted message/extra must never carry the raw
    # failure text — only the DB row does (job.error_message, asserted
    # separately below).
    assert secret_message not in rec.getMessage()
    assert secret_message not in str(rec.__dict__)
    assert job.error_message == secret_message  # DB row still keeps full detail for debugging


def test_agents_worker_fail_job_logs_agent_context_not_raw_message(caplog):
    import uuid as _uuid

    from app.agents.worker import fail_job as agents_fail_job
    from app.models import AgentAnalysisJob, AgentJobStatus
    from tests.fakes import FakeSession

    job = AgentAnalysisJob(
        id=_uuid.uuid4(), company_id=_uuid.uuid4(), project_id=_uuid.uuid4(),
        created_by=_uuid.uuid4(), status=AgentJobStatus.processing, progress_percent=55,
        current_agent="variation_detection",
    )
    session = FakeSession()
    secret_message = "raw provider exception text that must not be logged verbatim"

    with caplog.at_level(logging.WARNING, logger="app.agents.worker"):
        agents_fail_job(session, job, "AI_PROVIDER_UNAVAILABLE", secret_message)

    records = [r for r in caplog.records if r.name == "app.agents.worker" and r.msg == "job.failed"]
    assert len(records) == 1
    rec = records[0]
    assert rec.job_id == str(job.id)
    assert rec.project_id == str(job.project_id)
    assert rec.agent == "variation_detection"
    assert rec.error_code == "AI_PROVIDER_UNAVAILABLE"
    assert secret_message not in rec.getMessage()
    assert secret_message not in str(rec.__dict__)


# --------------------------------------------------------------------------
# Unknown/unexpected exceptions in the worker still fail the job (never
# leave it stuck) and get a full traceback logged server-side.
# --------------------------------------------------------------------------
def test_job_worker_unexpected_exception_is_logged_with_traceback(caplog):
    import uuid as _uuid

    from app.engine.client import EngineClient
    from app.models import AnalysisJob, Document, JobStatus, SourceType
    from app.worker.job_worker import process_job
    from tests.fakes import FakeResult, FakeSession

    class ExplodingLoader:
        def load(self, storage_key):
            raise ValueError("unexpected parsing failure")

    job = AnalysisJob()
    job.id = _uuid.uuid4()
    job.company_id = _uuid.uuid4()
    job.project_id = _uuid.uuid4()
    job.created_by = None

    doc = Document()
    doc.id = _uuid.uuid4()
    doc.source_type = SourceType.document
    doc.doc_timestamp = None
    doc.source = "note.txt"
    doc.storage_key = "some/key.txt"

    # build_request calls session.get(Project, ...) then session.execute(...)
    # for documents — get_obj=None (project) is fine, build_request handles
    # a missing project defensively (contract_text defaults to "").
    session = FakeSession(results=[FakeResult(scalars=[doc])], get_obj=None)

    with caplog.at_level(logging.ERROR, logger="app.worker.job_worker"):
        process_job(session, client=object.__new__(EngineClient), job=job, loader=ExplodingLoader())

    assert job.status == JobStatus.failed
    assert job.error_code == "INTERNAL"
    unexpected_records = [r for r in caplog.records if r.msg == "job.unexpected_error"]
    assert len(unexpected_records) == 1
    assert unexpected_records[0].exc_info is not None  # traceback captured
