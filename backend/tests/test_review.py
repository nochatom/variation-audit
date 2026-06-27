"""Commercial review workflow (.14): transitions, audit, comments, endpoints."""
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user, get_db
from app.main import app
from app.models import (
    AuditLog,
    ConfidenceBand,
    Membership,
    ReviewComment,
    ReviewStatus,
    User,
    Variation,
)
from app.services import review as review_service
from tests.fakes import FakeResult, FakeSession


def _user():
    return User(id=uuid.uuid4(), email="ca@firm.com", password_hash="x", is_active=True)


def _variation(status=ReviewStatus.pending, company_id=None):
    v = Variation(
        id=uuid.uuid4(), company_id=company_id or uuid.uuid4(), project_id=uuid.uuid4(),
        job_id=uuid.uuid4(), title="Extra GPOs", review_status=status,
        confidence_score=Decimal("0.82"), confidence_band=ConfidenceBand.high,
        time_bar_risk=False,
    )
    return v


# -- transitions -----------------------------------------------------------
def test_confirm_sets_reviewer_and_audits():
    user, v = _user(), _variation()
    session = FakeSession()
    review_service.set_review_status(session, v, user=user, new_status=ReviewStatus.confirmed)
    assert v.review_status == ReviewStatus.confirmed
    assert v.reviewed_by == user.id and v.reviewed_at is not None
    audits = session.added_of(AuditLog)
    assert len(audits) == 1 and audits[0].action == "review.confirmed"
    assert audits[0].before == {"review_status": "pending"}
    assert session.commits == 1


def test_reopen_clears_reviewer():
    user = _user()
    v = _variation(status=ReviewStatus.confirmed)
    v.reviewed_by = uuid.uuid4()
    review_service.set_review_status(FakeSession(), v, user=user, new_status=ReviewStatus.pending)
    assert v.review_status == ReviewStatus.pending
    assert v.reviewed_by is None and v.reviewed_at is None


def test_invalid_noop_transition_raises():
    with pytest.raises(review_service.InvalidTransition):
        review_service.set_review_status(FakeSession(), _variation(), user=_user(),
                                         new_status=ReviewStatus.pending)  # pending -> pending


def test_add_comment():
    user, v = _user(), _variation()
    session = FakeSession()
    c = review_service.add_comment(session, v, user=user, body="Looks legit, claim it.")
    assert isinstance(c, ReviewComment)
    assert c.variation_id == v.id and c.author_user_id == user.id
    assert session.added_of(ReviewComment) == [c]


# -- endpoints -------------------------------------------------------------
def _client(session, user):
    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_review_queue_endpoint():
    user = _user()
    cid = uuid.uuid4()
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid)
    v = _variation(company_id=cid)
    session = FakeSession(results=[FakeResult(scalar=membership), FakeResult(scalars=[v])])
    resp = _client(session, user).get(f"/projects/{v.project_id}/review-queue?company_id={cid}")
    assert resp.status_code == 200
    assert resp.json()[0]["title"] == "Extra GPOs"


def test_review_action_endpoint_confirms():
    user = _user()
    cid = uuid.uuid4()
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid)
    v = _variation(company_id=cid)
    # _load: session.get(Variation) -> v; ensure_member: execute -> membership
    session = FakeSession(results=[FakeResult(scalar=membership)], get_obj=v)
    resp = _client(session, user).post(f"/variations/{v.id}/review",
                                       json={"status": "confirmed"})
    assert resp.status_code == 200
    assert resp.json()["review_status"] == "confirmed"


def test_add_comment_endpoint():
    user = _user()
    cid = uuid.uuid4()
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid)
    v = _variation(company_id=cid)
    session = FakeSession(results=[FakeResult(scalar=membership)], get_obj=v)
    resp = _client(session, user).post(f"/variations/{v.id}/comments",
                                       json={"body": "Claim it."})
    assert resp.status_code == 201
    assert resp.json()["body"] == "Claim it."
