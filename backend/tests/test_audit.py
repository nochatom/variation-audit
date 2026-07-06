"""Audit trail & evidence viewer (.17): service + endpoints."""
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.auth.deps import get_current_user, get_db
from app.main import app
from app.models import (
    AuditLog,
    Document,
    Evidence,
    Membership,
    MembershipRole,
    PlanTier,
    SourceType,
    Subscription,
    SubscriptionStatus,
    User,
    Variation,
)
from app.services import audit as audit_service
from tests.fakes import FakeResult, FakeSession


def _user():
    return User(id=uuid.uuid4(), email="ca@firm.com", password_hash="x", is_active=True)


def _audit(cid, action="review.confirmed", entity_id=None):
    a = AuditLog(id=uuid.uuid4(), company_id=cid, actor_user_id=uuid.uuid4(),
                 entity_type="variation", entity_id=entity_id or uuid.uuid4(), action=action,
                 before={"review_status": "pending"}, after={"review_status": "confirmed"})
    a.created_at = datetime.now(timezone.utc)
    return a


# -- service ---------------------------------------------------------------
def test_list_audit_returns_rows():
    cid = uuid.uuid4()
    session = FakeSession(results=[FakeResult(scalars=[_audit(cid), _audit(cid)])])
    rows = audit_service.list_audit(session, cid)
    assert len(rows) == 2


def test_evidence_with_documents_pairs_source():
    vid, did = uuid.uuid4(), uuid.uuid4()
    ev = Evidence(id=uuid.uuid4(), variation_id=vid, source_type=SourceType.email,
                  source_document_id=did, reference="thread#3", quote="please proceed")
    doc = Document(id=did, company_id=uuid.uuid4(), project_id=uuid.uuid4(),
                   source_type=SourceType.email, source="J. Smith", storage_key="k1")
    # query order: evidence, then documents
    session = FakeSession(results=[FakeResult(scalars=[ev]), FakeResult(scalars=[doc])])
    pairs = audit_service.evidence_with_documents(session, vid)
    assert len(pairs) == 1
    e, d = pairs[0]
    assert e.quote == "please proceed" and d is not None and d.source == "J. Smith"


def test_evidence_without_source_document():
    vid = uuid.uuid4()
    ev = Evidence(id=uuid.uuid4(), variation_id=vid, source_type=SourceType.sms,
                  source_document_id=None, reference=None, quote="verbal go-ahead")
    session = FakeSession(results=[FakeResult(scalars=[ev]), FakeResult(scalars=[])])
    pairs = audit_service.evidence_with_documents(session, vid)
    assert pairs[0][1] is None


# -- endpoints -------------------------------------------------------------
def _client(session, user):
    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def _variation(cid):
    return Variation(id=uuid.uuid4(), company_id=cid, project_id=uuid.uuid4(),
                     job_id=uuid.uuid4(), title="V")


def test_org_audit_requires_admin():
    user, cid = _user(), uuid.uuid4()
    member = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid, role=MembershipRole.member)
    resp = _client(FakeSession(results=[FakeResult(scalar=member)]), user).get(f"/audit?company_id={cid}")
    assert resp.status_code == 403


def test_org_audit_admin_ok():
    user, cid = _user(), uuid.uuid4()
    admin = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid, role=MembershipRole.admin)
    sub = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.pro,
                       status=SubscriptionStatus.active)
    session = FakeSession(results=[
        FakeResult(scalar=admin),
        FakeResult(scalar=sub),           # enforce_feature("audit_log") -> get_or_create_subscription
        FakeResult(scalars=[_audit(cid)]),
    ])
    resp = _client(session, user).get(f"/audit?company_id={cid}")
    assert resp.status_code == 200 and resp.json()[0]["action"] == "review.confirmed"


def test_org_audit_403_for_free_plan():
    """The org-wide audit trail is a paid-plan feature (.25) — Free orgs get
    a clear 403 rather than seeing an empty (or real) audit trail."""
    user, cid = _user(), uuid.uuid4()
    admin = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid, role=MembershipRole.admin)
    sub = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.free,
                       status=SubscriptionStatus.active)
    session = FakeSession(results=[FakeResult(scalar=admin), FakeResult(scalar=sub)])
    resp = _client(session, user).get(f"/audit?company_id={cid}")
    assert resp.status_code == 403


def test_variation_evidence_endpoint():
    user, cid = _user(), uuid.uuid4()
    v = _variation(cid)
    member = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid)
    did = uuid.uuid4()
    ev = Evidence(id=uuid.uuid4(), variation_id=v.id, source_type=SourceType.email,
                  source_document_id=did, reference="r", quote="q")
    doc = Document(id=did, company_id=cid, project_id=v.project_id,
                   source_type=SourceType.email, source="J", storage_key="k")
    # _load_variation: get(Variation)->v ; ensure_member execute->member
    # then evidence_with_documents: evidence, documents
    session = FakeSession(results=[FakeResult(scalar=member),
                                   FakeResult(scalars=[ev]), FakeResult(scalars=[doc])],
                          get_obj=v)
    resp = _client(session, user).get(f"/variations/{v.id}/evidence")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["quote"] == "q" and body[0]["source_document"]["source"] == "J"
