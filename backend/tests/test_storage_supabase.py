"""Unit tests for SupabaseStorageLoader (app/storage.py) — mocked via
httpx.MockTransport, no real network calls, no supabase-py dependency."""
from __future__ import annotations

import httpx
import pytest

from app.storage import SupabaseStorageLoader, build_loader


def _loader(handler) -> SupabaseStorageLoader:
    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer test-service-role-key", "apikey": "test-service-role-key"},
    )
    return SupabaseStorageLoader(
        project_url="https://project.supabase.co",
        service_role_key="test-service-role-key",
        bucket="project-documents",
        client=client,
    )


def test_put_sends_correct_url_and_auth_headers():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["apikey"] = request.headers.get("apikey")
        captured["body"] = request.content
        return httpx.Response(200, json={"Key": "ok"})

    loader = _loader(handler)

    key = loader.put("company/project/docs/abc.txt", "hello world")

    assert key == "company/project/docs/abc.txt"
    assert captured["url"] == "https://project.supabase.co/storage/v1/object/project-documents/company/project/docs/abc.txt"
    assert captured["auth"] == "Bearer test-service-role-key"
    assert captured["apikey"] == "test-service-role-key"
    assert captured["body"] == b"hello world"


def test_put_encodes_str_and_passes_bytes_through():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    loader = _loader(handler)
    loader.put("k1", "text content")
    loader.put("k2", b"\x00\x01raw-bytes")  # should pass through unchanged, no crash


def test_put_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "Unauthorized"})

    loader = _loader(handler)
    with pytest.raises(httpx.HTTPStatusError):
        loader.put("some/key.txt", "data")


def test_load_returns_decoded_text():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"stored document content")

    loader = _loader(handler)
    result = loader.load("company/project/docs/abc.txt")
    assert result == "stored document content"


def test_load_raises_on_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"})

    loader = _loader(handler)
    with pytest.raises(httpx.HTTPStatusError):
        loader.load("missing/key.txt")


def test_delete_is_idempotent_on_404():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"})

    loader = _loader(handler)
    loader.delete("already/gone.txt")  # must not raise


def test_delete_raises_on_real_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "internal error"})

    loader = _loader(handler)
    with pytest.raises(httpx.HTTPStatusError):
        loader.delete("some/key.txt")


def test_delete_succeeds_on_200():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"name": "some/key.txt"}])

    loader = _loader(handler)
    loader.delete("some/key.txt")  # must not raise


# --------------------------------------------------------------------------
# build_loader() wiring
# --------------------------------------------------------------------------
def test_build_loader_prefers_local_dir_over_supabase(monkeypatch):
    from app import config

    class FakeSettings:
        local_doc_dir = "/tmp/docs"
        supabase_url = "https://project.supabase.co"
        supabase_service_role_key = "key"
        supabase_storage_bucket = "project-documents"

    monkeypatch.setattr(config, "get_settings", lambda: FakeSettings())
    from app.storage import LocalDocumentLoader

    loader = build_loader()
    assert isinstance(loader, LocalDocumentLoader)


def test_build_loader_uses_supabase_when_configured_and_no_local_dir(monkeypatch):
    from app import config

    class FakeSettings:
        local_doc_dir = None
        supabase_url = "https://project.supabase.co"
        supabase_service_role_key = "key"
        supabase_storage_bucket = "project-documents"

    monkeypatch.setattr(config, "get_settings", lambda: FakeSettings())

    loader = build_loader()
    assert isinstance(loader, SupabaseStorageLoader)
    assert loader.bucket == "project-documents"


def test_build_loader_falls_back_to_s3_when_supabase_not_configured(monkeypatch):
    pytest.importorskip("boto3", reason="boto3 not installed in this environment")
    from app import config

    class FakeSettings:
        local_doc_dir = None
        supabase_url = None
        supabase_service_role_key = None
        supabase_storage_bucket = "project-documents"
        s3_bucket = "va-bucket"
        s3_region = "ap-southeast-2"
        s3_endpoint_url = None

    monkeypatch.setattr(config, "get_settings", lambda: FakeSettings())
    from app.storage import S3DocumentLoader

    loader = build_loader()
    assert isinstance(loader, S3DocumentLoader)
