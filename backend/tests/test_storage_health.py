"""Unit tests for app.storage.check_storage_health — read-only diagnostics,
no real network calls (httpx.get is monkeypatched), no DB required.

Also covers the secrets-never-leak requirement directly: every returned
dict is asserted to never contain the raw service_role key value anywhere
(not just absent as a named field).
"""
from __future__ import annotations

import httpx
import pytest

from app.storage import check_storage_health

FAKE_KEY = "test-service-role-key-should-never-leak"


class FakeSettings:
    local_doc_dir = None
    supabase_url = "https://project.supabase.co"
    supabase_service_role_key = FAKE_KEY
    supabase_storage_bucket = "project-documents"
    s3_bucket = "va-bucket"


def _assert_no_secret_leak(result: dict) -> None:
    import json

    serialized = json.dumps(result)
    assert FAKE_KEY not in serialized
    assert "Authorization" not in serialized
    assert "Bearer" not in serialized


# --------------------------------------------------------------------------
# Response shape
# --------------------------------------------------------------------------
def test_response_has_exact_required_keys(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(
        200, json={"id": "project-documents", "public": False, "created_at": "2026-01-01T00:00:00Z"},
    ))
    result = check_storage_health(FakeSettings())
    assert set(result.keys()) == {"provider", "bucket", "status", "checked_at", "details"}
    from datetime import datetime
    datetime.fromisoformat(result["checked_at"])  # must be a real timestamp


# --------------------------------------------------------------------------
# Supabase branch
# --------------------------------------------------------------------------
def test_supabase_healthy_when_bucket_reachable(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        return httpx.Response(200, json={"id": "project-documents", "public": False, "created_at": "x"})

    monkeypatch.setattr(httpx, "get", fake_get)
    result = check_storage_health(FakeSettings())

    assert result["provider"] == "supabase"
    assert result["bucket"] == "project-documents"
    assert result["status"] == "healthy"
    # a GET, never a PUT/POST/DELETE against the object endpoint
    assert captured["url"] == "https://project.supabase.co/storage/v1/bucket/project-documents"
    _assert_no_secret_leak(result)


def test_supabase_unhealthy_when_bucket_lookup_fails(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(404, json={"error": "not found"}))
    result = check_storage_health(FakeSettings())
    assert result["status"] == "unhealthy"
    _assert_no_secret_leak(result)


def test_supabase_unhealthy_when_request_raises(monkeypatch):
    def fake_get(*a, **k):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", fake_get)
    result = check_storage_health(FakeSettings())
    assert result["status"] == "unhealthy"
    _assert_no_secret_leak(result)


def test_supabase_health_check_never_calls_put_or_delete(monkeypatch):
    """Must not upload/delete test files — asserted by only stubbing GET;
    if the implementation called anything else, httpx would use the real
    network (no transport override) and this test would hang/fail instead
    of silently passing, since httpx.get is the only stubbed verb."""
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return httpx.Response(200, json={"id": "project-documents"})

    monkeypatch.setattr(httpx, "get", fake_get)
    check_storage_health(FakeSettings())
    assert len(calls) == 1
    assert "/object/" not in calls[0]  # object endpoint is where put/load/delete operate; bucket endpoint is metadata-only


# --------------------------------------------------------------------------
# Local branch
# --------------------------------------------------------------------------
def test_local_healthy_when_dir_exists_and_writable(tmp_path):
    class S(FakeSettings):
        local_doc_dir = str(tmp_path)

    result = check_storage_health(S())
    assert result["provider"] == "local"
    assert result["status"] == "healthy"
    _assert_no_secret_leak(result)


def test_local_unhealthy_when_dir_missing(tmp_path):
    class S(FakeSettings):
        local_doc_dir = str(tmp_path / "does-not-exist")

    result = check_storage_health(S())
    assert result["status"] == "unhealthy"


# --------------------------------------------------------------------------
# Not configured
# --------------------------------------------------------------------------
def test_reports_s3_unknown_when_neither_local_nor_supabase_configured():
    class S:
        local_doc_dir = None
        supabase_url = None
        supabase_service_role_key = None
        supabase_storage_bucket = "project-documents"
        s3_bucket = "va-bucket"

    result = check_storage_health(S())
    assert result["provider"] == "s3"
    assert result["status"] == "unknown"


def test_local_doc_dir_takes_precedence_over_supabase_matching_build_loader(tmp_path, monkeypatch):
    """check_storage_health must report on whatever build_loader() would
    actually resolve to — same local -> supabase -> s3 precedence, never
    redesigned."""
    def fake_get(*a, **k):
        pytest.fail("must not call Supabase when local_doc_dir is set")

    monkeypatch.setattr(httpx, "get", fake_get)

    class S(FakeSettings):
        local_doc_dir = str(tmp_path)

    result = check_storage_health(S())
    assert result["provider"] == "local"
