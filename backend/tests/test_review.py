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
    Project,
    ProjectStatus,
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
    project = Project(id=v.project_id, company_id=cid, name="Tower A",
                      status=ProjectStatus.in_progress)
    # session.get(Project, ...) -> project ; ensure_member execute -> membership ; queue -> [v]
    session = FakeSession(results=[FakeResult(scalar=membership), FakeResult(scalars=[v])],
                          get_obj=project)
    resp = _client(session, user).get(f"/projects/{v.project_id}/review-queue?company_id={cid}")
    assert resp.status_code == 200
    assert resp.json()[0]["title"] == "Extra GPOs"


def test_review_queue_endpoint_ignores_mismatched_company_id_param():
    """Object-level authorization: the owning org is derived from the project,
    not the caller-supplied company_id — a mismatched value must not matter."""
    user = _user()
    cid = uuid.uuid4()
    other_cid = uuid.uuid4()  # attacker's own org — different from the project's
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid)
    v = _variation(company_id=cid)
    project = Project(id=v.project_id, company_id=cid, name="Tower A",
                      status=ProjectStatus.in_progress)
    session = FakeSession(results=[FakeResult(scalar=membership), FakeResult(scalars=[v])],
                          get_obj=project)
    resp = _client(session, user).get(f"/projects/{v.project_id}/review-queue?company_id={other_cid}")
    assert resp.status_code == 200  # authorized via the real project.company_id, not the param


def test_review_queue_endpoint_unknown_project_404s():
    user = _user()
    session = FakeSession(get_obj=None)
    resp = _client(session, user).get(f"/projects/{uuid.uuid4()}/review-queue")
    assert resp.status_code == 404


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


# -- queue value ------------------------------------------------------------
# The money lives in value_estimates, not on the Variation row, so a summary
# built from the variation alone reported amount=None for every queue row —
# which made the review queue total $0 while the detail page showed real
# figures for the same variations.
def test_amounts_for_maps_variation_to_likely_value():
    a, b = uuid.uuid4(), uuid.uuid4()
    session = FakeSession(results=[FakeResult(rows=[(a, Decimal("38000.00")),
                                                   (b, Decimal("1250.50"))])])
    assert review_service.amounts_for(session, [a, b]) == {a: 38000.0, b: 1250.5}


def test_amounts_for_preserves_null_amount():
    """A row can exist with no amount — that must stay None, not become 0.0,
    so the UI can say "no value yet" instead of "worth nothing"."""
    vid = uuid.uuid4()
    session = FakeSession(results=[FakeResult(rows=[(vid, None)])])
    assert review_service.amounts_for(session, [vid]) == {vid: None}


def test_amounts_for_empty_input_runs_no_query():
    session = FakeSession()
    assert review_service.amounts_for(session, []) == {}


def test_review_queue_endpoint_carries_value():
    user = _user()
    cid = uuid.uuid4()
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid)
    v = _variation(company_id=cid)
    project = Project(id=v.project_id, company_id=cid, name="Tower A",
                      status=ProjectStatus.in_progress)
    # ensure_member -> membership ; queue -> [v] ; amounts_for -> one (id, amount) row
    session = FakeSession(
        results=[FakeResult(scalar=membership),
                 FakeResult(scalars=[v]),
                 FakeResult(rows=[(v.id, Decimal("38000.00"))])],
        get_obj=project,
    )
    resp = _client(session, user).get(f"/projects/{v.project_id}/review-queue")
    assert resp.status_code == 200
    assert resp.json()[0]["amount"] == 38000.0


def test_review_queue_endpoint_amount_none_when_unvalued():
    """A variation with no estimate must report null, not 0 — the queue's
    total would otherwise read as a real figure built from absent data."""
    user = _user()
    cid = uuid.uuid4()
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid)
    v = _variation(company_id=cid)
    project = Project(id=v.project_id, company_id=cid, name="Tower A",
                      status=ProjectStatus.in_progress)
    session = FakeSession(
        results=[FakeResult(scalar=membership), FakeResult(scalars=[v]), FakeResult(rows=[])],
        get_obj=project,
    )
    resp = _client(session, user).get(f"/projects/{v.project_id}/review-queue")
    assert resp.status_code == 200
    assert resp.json()[0]["amount"] is None
