"""Security response headers — applied to every response via middleware."""
from fastapi.testclient import TestClient

from app.main import app


def test_security_headers_present_on_every_response():
    resp = TestClient(app).get("/health")
    assert resp.status_code == 200
    assert resp.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert "camera=()" in resp.headers["permissions-policy"]
    assert resp.headers["cross-origin-opener-policy"] == "same-origin"
    assert resp.headers["strict-transport-security"].startswith("max-age=")


def test_security_headers_present_on_error_responses_too():
    resp = TestClient(app).get("/auth/me")  # 401, no auth header
    assert resp.status_code == 401
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" in resp.headers
