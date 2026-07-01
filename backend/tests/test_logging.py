"""Structured (JSON) logging: formatter, request middleware, security events."""
import json
import logging

from fastapi.testclient import TestClient

from app.logging_config import JsonFormatter, security_logger
from app.main import app


# -- JsonFormatter ------------------------------------------------------------
def test_json_formatter_produces_valid_json_with_extra_fields():
    record = logging.LogRecord(
        name="va.security", level=logging.INFO, pathname=__file__, lineno=1,
        msg="login succeeded", args=(), exc_info=None,
    )
    record.event = "login_succeeded"
    record.user_id = "abc-123"
    line = JsonFormatter().format(record)
    parsed = json.loads(line)  # raises if not valid JSON
    assert parsed["message"] == "login succeeded"
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "va.security"
    assert parsed["event"] == "login_succeeded"
    assert parsed["user_id"] == "abc-123"
    assert "timestamp" in parsed


def test_json_formatter_includes_exception_info():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        record = logging.LogRecord(
            name="va.test", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="failed", args=(), exc_info=sys.exc_info(),
        )
    line = JsonFormatter().format(record)
    parsed = json.loads(line)
    assert "ValueError" in parsed["exc_info"]


# -- request logging middleware -----------------------------------------------
def test_request_logging_adds_request_id_header():
    resp = TestClient(app).get("/health")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers
    assert len(resp.headers["X-Request-ID"]) == 32  # uuid4().hex


def test_request_logging_emits_structured_line(caplog):
    with caplog.at_level(logging.INFO, logger="va.request"):
        TestClient(app).get("/health")
    records = [r for r in caplog.records if r.name == "va.request"]
    assert len(records) == 1
    assert records[0].event == "http_request"
    assert records[0].status_code == 200
    assert records[0].method == "GET"
    assert records[0].path == "/health"
    assert isinstance(records[0].duration_ms, float)


def test_request_logging_elevates_auth_failures_to_warning(caplog):
    with caplog.at_level(logging.INFO, logger="va.request"):
        TestClient(app).get("/auth/me")  # 401, no auth header
    records = [r for r in caplog.records if r.name == "va.request"]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert records[0].status_code == 401


# -- security event logs from auth flows ---------------------------------------
def test_login_failure_logs_security_event(caplog):
    from app.auth.deps import get_db
    from tests.fakes import FakeResult, FakeSession

    session = FakeSession(results=[FakeResult(scalar=None)])

    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    try:
        with caplog.at_level(logging.INFO, logger="va.security"):
            TestClient(app).post("/auth/login", json={"email": "nope@x.com", "password": "wrongpass1"})
    finally:
        app.dependency_overrides.clear()

    events = [r.event for r in caplog.records if r.name == "va.security"]
    assert "login_failed" in events
