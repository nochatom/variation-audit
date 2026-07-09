"""OWASP hardening: input validation limits, upload size caps, rate limiting."""
import uuid

from fastapi.testclient import TestClient

from app.auth.deps import get_current_user, get_db
from app.main import app
from app.models import Membership, Project, ProjectStatus, User
from app.rate_limit import limiter
from app.storage import get_store
from tests.fakes import FakeResult, FakeSession


class FakeStore:
    def put(self, key, data):
        return key


def _project_client():
    user = User(id=uuid.uuid4(), email="ca@firm.com", password_hash="x", is_active=True)
    cid = uuid.uuid4()
    project = Project(id=uuid.uuid4(), company_id=cid, name="Tower A",
                      status=ProjectStatus.in_progress)
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid)
    # scalar= satisfies ensure_member's scalar_one_or_none(); scalars= satisfies
    # _load_project's scalars().all() — different endpoints use different queries.
    session = FakeSession(results=[FakeResult(scalar=membership, scalars=[membership])],
                          get_obj=project)

    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_store] = lambda: FakeStore()
    return TestClient(app), project


def teardown_function():
    app.dependency_overrides.clear()


# -- upload size cap ---------------------------------------------------------
def test_oversized_rfi_csv_upload_rejected():
    client, project = _project_client()
    oversized = b"a" * (11 * 1024 * 1024)  # 11MB > 10MB cap; content need not parse
    resp = client.post(f"/projects/{project.id}/rfis", files={"file": ("rfis.csv", oversized, "text/csv")})
    assert resp.status_code == 413


# -- upload parse hardening (.26 security fixes) ------------------------------
def test_contract_upload_malformed_pdf_returns_400_not_500():
    """A corrupt (or fake) PDF must be a clean 400 — previously pypdf's
    exception propagated as an unhandled 500."""
    client, project = _project_client()
    resp = client.post(f"/projects/{project.id}/contract",
                       files={"file": ("contract.pdf", b"not a real pdf", "application/pdf")})
    assert resp.status_code == 400


def test_contract_upload_pdf_name_with_non_pdf_content_type_rejected():
    client, project = _project_client()
    resp = client.post(f"/projects/{project.id}/contract",
                       files={"file": ("contract.pdf", b"<html>", "text/html")})
    assert resp.status_code == 400


def test_contract_upload_oversized_extracted_text_rejected():
    """The upload path must not bypass the 500KB contract_text cap the JSON
    create path enforces."""
    client, project = _project_client()
    big_text = b"a" * 600_000   # under the 20MB raw cap, over the text cap
    resp = client.post(f"/projects/{project.id}/contract",
                       files={"file": ("contract.txt", big_text, "text/plain")})
    assert resp.status_code == 413


def _valid_pdf_bytes() -> bytes:
    """A real (blank single-page) PDF generated with the same library the
    parser uses — genuinely valid, not a handcrafted approximation."""
    import io
    from pypdf import PdfWriter

    buf = io.BytesIO()
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.write(buf)
    return buf.getvalue()


def _upload_client():
    """_project_client plus the extra queued results the contract-upload
    storage check consumes (subscription lookup -> lazily-created Free sub,
    then the aggregated storage-bytes scalar)."""
    user = User(id=uuid.uuid4(), email="ca@firm.com", password_hash="x", is_active=True)
    cid = uuid.uuid4()
    project = Project(id=uuid.uuid4(), company_id=cid, name="Tower A",
                      status=ProjectStatus.in_progress)
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid)
    session = FakeSession(results=[FakeResult(scalar=membership, scalars=[membership]),
                                   FakeResult(scalar=None),
                                   FakeResult(scalar=0)],
                          get_obj=project)

    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_store] = lambda: FakeStore()
    return TestClient(app), project


def test_contract_upload_valid_pdf_accepted():
    client, project = _upload_client()
    resp = client.post(f"/projects/{project.id}/contract",
                       files={"file": ("contract.pdf", _valid_pdf_bytes(), "application/pdf")})
    assert resp.status_code == 200


def test_contract_upload_valid_pdf_wrong_content_type_rejected():
    client, project = _project_client()
    resp = client.post(f"/projects/{project.id}/contract",
                       files={"file": ("contract.pdf", _valid_pdf_bytes(), "text/html")})
    assert resp.status_code == 400


def test_contract_upload_pdf_content_type_but_junk_bytes_rejected():
    """Correct content type must not be enough — magic bytes are checked."""
    client, project = _project_client()
    resp = client.post(f"/projects/{project.id}/contract",
                       files={"file": ("contract.pdf", b"MZ\x90\x00 definitely not pdf", "application/pdf")})
    assert resp.status_code == 400


def test_contract_upload_pdf_header_but_malformed_body_rejected():
    """Magic bytes alone must not be enough either — the parser pass catches
    a file that fakes the %PDF- header but has no valid structure."""
    client, project = _project_client()
    resp = client.post(f"/projects/{project.id}/contract",
                       files={"file": ("contract.pdf", b"%PDF-1.7\ngarbage" * 3, "application/pdf")})
    assert resp.status_code == 400


def test_mailer_header_values_strip_crlf():
    """Org/user names are user input that flows into email headers — CR/LF
    must be stripped so a crafted name can't inject additional headers."""
    from app.mailer import _header_safe

    assert _header_safe("Evil\r\nBcc: victim@x.com") == "EvilBcc: victim@x.com"
    assert _header_safe("Normal Org Pty Ltd") == "Normal Org Pty Ltd"


# -- project input validation -------------------------------------------------
def test_create_project_rejects_invalid_state():
    client, _ = _project_client()
    resp = client.post("/projects", json={
        "company_id": str(uuid.uuid4()), "name": "Tower A", "state": "XX",
    })
    assert resp.status_code == 422


def test_create_project_rejects_blank_name():
    client, _ = _project_client()
    resp = client.post("/projects", json={"company_id": str(uuid.uuid4()), "name": "   "})
    assert resp.status_code == 422


def test_create_project_accepts_valid_au_state(monkeypatch):
    client, project = _project_client()
    created = Project(id=uuid.uuid4(), company_id=project.company_id, name="Tower A",
                      state="VIC", status=ProjectStatus.in_progress)
    import app.services.projects as project_service
    monkeypatch.setattr(project_service, "create_project", lambda *a, **k: created)
    resp = client.post("/projects", json={
        "company_id": str(project.company_id), "name": "Tower A", "state": "vic",
    })
    assert resp.status_code == 201
    assert resp.json()["state"] == "VIC"


# -- comment validation --------------------------------------------------------
def _variation_client():
    user = User(id=uuid.uuid4(), email="ca@firm.com", password_hash="x", is_active=True)
    session = FakeSession(get_obj=None)  # not reached — validation fails first

    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_add_comment_rejects_blank_body():
    v = uuid.UUID(int=1)
    resp = _variation_client().post(f"/variations/{v}/comments", json={"body": "   "})
    assert resp.status_code == 422


def test_add_comment_rejects_oversized_body():
    v = uuid.UUID(int=1)
    resp = _variation_client().post(f"/variations/{v}/comments", json={"body": "x" * 5001})
    assert resp.status_code == 422


# -- auth password policy ------------------------------------------------------
def test_signup_rejects_short_password():
    session = FakeSession(results=[FakeResult(scalar=None)])

    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    resp = TestClient(app).post("/auth/signup", json={
        "email": "new@firm.com.au", "password": "short", "org_name": "Acme",
    })
    assert resp.status_code == 422


# -- rate limiting --------------------------------------------------------------
def test_login_rate_limited_after_5_attempts():
    limiter.reset()  # isolate from other tests' auth-endpoint calls
    try:
        session = FakeSession(results=[FakeResult(scalar=None)])

        def _db():
            yield session
        app.dependency_overrides[get_db] = _db
        client = TestClient(app)
        payload = {"email": "nope@firm.com", "password": "wrong1234"}
        responses = [client.post("/auth/login", json=payload) for _ in range(6)]
        statuses = [r.status_code for r in responses]
        assert statuses[:5] == [401, 401, 401, 401, 401]  # invalid creds, but allowed through
        assert statuses[5] == 429                          # 6th request in the same minute: rate-limited
        # headers_enabled=True: well-behaved clients get told when to retry
        assert "retry-after" in responses[5].headers
    finally:
        limiter.reset()


def _project_client_n(n: int, contract_text: str | None = None):
    """Like _project_client but survives `n` requests (one execute per request)."""
    user = User(id=uuid.uuid4(), email="ca@firm.com", password_hash="x", is_active=True)
    cid = uuid.uuid4()
    project = Project(id=uuid.uuid4(), company_id=cid, name="Tower A",
                      contract_text=contract_text, status=ProjectStatus.in_progress)
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid)
    session = FakeSession(
        results=[FakeResult(scalar=membership, scalars=[membership]) for _ in range(n)],
        get_obj=project,
    )

    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_store] = lambda: FakeStore()
    return TestClient(app), project


def test_uploads_rate_limited_after_20_per_minute(monkeypatch):
    from app.routers import projects as projects_router

    limiter.reset()
    try:
        client, project = _project_client_n(25)
        # This test is about per-IP rate limiting, not plan usage limits —
        # bypass the (separately unit-tested) plan-limit checks so 20
        # uploads in a minute don't trip the Free plan's document/storage caps.
        monkeypatch.setattr(projects_router.billing_service, "enforce_document_limit", lambda *a, **k: None)
        monkeypatch.setattr(projects_router.billing_service, "enforce_storage_limit", lambda *a, **k: None)
        csv = b"rfi_number,subject,question\nR1,Subject,Question\n"
        statuses = [
            client.post(f"/projects/{project.id}/rfis",
                        files={"file": ("rfis.csv", csv, "text/csv")}).status_code
            for _ in range(21)
        ]
        assert statuses[:20] == [200] * 20
        assert statuses[20] == 429
    finally:
        limiter.reset()


def test_analysis_rate_limited_after_10_per_hour(monkeypatch):
    from types import SimpleNamespace

    from app.models import JobStatus
    from app.routers import projects as projects_router

    limiter.reset()
    try:
        client, project = _project_client_n(15, contract_text="Agreed scope baseline.")
        monkeypatch.setattr(
            projects_router.jobs, "enqueue_analysis",
            lambda *a, **k: SimpleNamespace(id=uuid.uuid4(), status=JobStatus.queued),
        )
        # This test is about per-IP rate limiting, not plan usage limits —
        # bypass the (separately unit-tested) plan-limit check so 10 calls
        # in an hour don't trip the Free plan's 5-analysis-run/month cap.
        monkeypatch.setattr(projects_router.billing_service, "enforce_analysis_limit", lambda *a, **k: None)
        statuses = [client.post(f"/projects/{project.id}/analyze").status_code for _ in range(11)]
        assert statuses[:10] == [202] * 10
        assert statuses[10] == 429
    finally:
        limiter.reset()


def test_health_exempt_from_rate_limiting():
    # LB probes must never be throttled. The volume check alone can't prove
    # the exemption under the relaxed test default, so also assert /health is
    # registered in the limiter's exempt set.
    assert "app.main.health" in limiter._exempt_routes
    client = TestClient(app)
    assert all(client.get("/health").status_code == 200 for _ in range(30))


def test_configured_limits_use_valid_grammar():
    # A typo'd VA_RATE_LIMIT_* env value should fail here, not at first 429.
    from limits import parse

    from app.config import get_settings

    s = get_settings()
    for value in (s.rate_limit_default, s.rate_limit_auth,
                  s.rate_limit_uploads, s.rate_limit_analysis):
        parse(value)  # raises ValueError on bad grammar
