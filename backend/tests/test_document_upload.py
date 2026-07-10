"""Tests for POST /projects/{id}/documents — the single-file document
upload endpoint backed by app.storage's DocumentLoader (Supabase Storage in
production, FakeStore here)."""
from __future__ import annotations

import io
import uuid

from fastapi.testclient import TestClient

from app.auth.deps import get_current_user, get_db
from app.main import app
from app.models import Document, Membership, Project, ProjectStatus, SourceType, User
from app.storage import get_store
from tests.fakes import FakeResult, FakeSession


class FakeStore:
    def __init__(self, fail: bool = False):
        self.puts: list[tuple[str, str]] = []
        self.fail = fail

    def put(self, key, data):
        if self.fail:
            raise ConnectionError("simulated Supabase Storage outage")
        self.puts.append((key, data))
        return key


def _client(store: FakeStore | None = None):
    user = User(id=uuid.uuid4(), email="ca@firm.com", password_hash="x", is_active=True)
    cid = uuid.uuid4()
    project = Project(id=uuid.uuid4(), company_id=cid, name="Tower A",
                      status=ProjectStatus.in_progress)
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid)
    session = FakeSession(results=[FakeResult(scalars=[membership])], get_obj=project)

    def _db():
        yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_store] = lambda: (store if store is not None else FakeStore())
    return TestClient(app), project, session


def teardown_function():
    app.dependency_overrides.clear()


def _valid_pdf_bytes() -> bytes:
    from pypdf import PdfWriter

    buf = io.BytesIO()
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.write(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------
def test_upload_document_valid_pdf_creates_document_row_and_stores_it():
    store = FakeStore()
    client, project, session = _client(store)

    resp = client.post(f"/projects/{project.id}/documents",
                       files={"file": ("evidence.pdf", _valid_pdf_bytes(), "application/pdf")})

    assert resp.status_code == 201
    body = resp.json()
    assert body["project_id"] == str(project.id)
    assert body["source_type"] == "document"
    assert len(store.puts) == 1
    assert session.added_of(Document)[0].source_type == SourceType.document
    assert session.added_of(Document)[0].source == "evidence.pdf"


def test_upload_document_plain_text_accepted():
    store = FakeStore()
    client, project, session = _client(store)

    resp = client.post(f"/projects/{project.id}/documents",
                       files={"file": ("note.txt", b"a site note", "text/plain")})

    assert resp.status_code == 201
    assert len(store.puts) == 1


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def test_upload_document_empty_file_rejected():
    client, project, _ = _client()
    resp = client.post(f"/projects/{project.id}/documents",
                       files={"file": ("empty.txt", b"", "text/plain")})
    assert resp.status_code == 400


def test_upload_document_malformed_pdf_returns_400():
    client, project, _ = _client()
    resp = client.post(f"/projects/{project.id}/documents",
                       files={"file": ("doc.pdf", b"not a real pdf", "application/pdf")})
    assert resp.status_code == 400


def test_upload_document_pdf_name_wrong_content_type_rejected():
    client, project, _ = _client()
    resp = client.post(f"/projects/{project.id}/documents",
                       files={"file": ("doc.pdf", b"<html>", "text/html")})
    assert resp.status_code == 400


def test_upload_document_pdf_header_but_junk_body_rejected():
    client, project, _ = _client()
    resp = client.post(f"/projects/{project.id}/documents",
                       files={"file": ("doc.pdf", b"%PDF-1.7\ngarbage" * 3, "application/pdf")})
    assert resp.status_code == 400


def test_upload_document_oversized_extracted_text_rejected():
    client, project, _ = _client()
    big_text = b"a" * 600_000  # over MAX_TEXT_LEN, under the raw upload cap
    resp = client.post(f"/projects/{project.id}/documents",
                       files={"file": ("note.txt", big_text, "text/plain")})
    assert resp.status_code == 413


def test_upload_document_oversized_raw_file_rejected():
    client, project, _ = _client()
    oversized = b"a" * (21 * 1024 * 1024)  # over the 20MB raw cap
    resp = client.post(f"/projects/{project.id}/documents",
                       files={"file": ("big.txt", oversized, "text/plain")})
    assert resp.status_code == 413


# --------------------------------------------------------------------------
# AuthN/authZ
# --------------------------------------------------------------------------
def test_upload_document_requires_authentication():
    app.dependency_overrides.clear()
    client = TestClient(app)
    resp = client.post(f"/projects/{uuid.uuid4()}/documents",
                       files={"file": ("note.txt", b"hi", "text/plain")})
    assert resp.status_code in (401, 403)


def test_upload_document_rejects_non_member_project():
    """A project not visible to the caller's memberships -> 404, not 403 —
    matches _load_project's existing "don't reveal existence" behavior."""
    user = User(id=uuid.uuid4(), email="ca@firm.com", password_hash="x", is_active=True)
    other_project = Project(id=uuid.uuid4(), company_id=uuid.uuid4(), name="Other Co Tower",
                            status=ProjectStatus.in_progress)
    # caller has no memberships at all -> company_ids == []
    session = FakeSession(results=[FakeResult(scalars=[])], get_obj=other_project)

    def _db():
        yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_store] = lambda: FakeStore()
    client = TestClient(app)

    resp = client.post(f"/projects/{other_project.id}/documents",
                       files={"file": ("note.txt", b"hi", "text/plain")})
    assert resp.status_code == 404


# --------------------------------------------------------------------------
# Error handling — object storage failure
# --------------------------------------------------------------------------
def test_upload_document_storage_failure_returns_502_not_500():
    store = FakeStore(fail=True)
    client, project, _ = _client(store)

    resp = client.post(f"/projects/{project.id}/documents",
                       files={"file": ("note.txt", b"hello", "text/plain")})

    assert resp.status_code == 502
