"""Billing & subscriptions (.23): usage, checkout/portal, cancel, webhook, RBAC."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth.deps import get_current_user, get_db, require_admin
from app.billing.provider import BillingNotConfigured, CheckoutSession, PortalSession
from app.main import app
from app.models import (
    Invoice,
    InvoiceStatus,
    Membership,
    MembershipRole,
    Organization,
    PlanTier,
    Subscription,
    SubscriptionStatus,
    User,
)
from app.services import billing as billing_service
from tests.fakes import FakeResult, FakeSession


class _FakeProvider:
    def __init__(self):
        self.canceled = []

    def get_or_create_customer(self, *, company_id, email, name):
        return "cus_fake123"

    def create_checkout_session(self, *, customer_id, price_id, success_url, cancel_url,
                                client_reference_id, idempotency_key=None):
        self.last_idempotency_key = idempotency_key
        return CheckoutSession(url=f"https://checkout.stripe.com/fake?price={price_id}")

    def create_billing_portal_session(self, *, customer_id, return_url):
        return PortalSession(url="https://billing.stripe.com/fake-portal")

    def cancel_subscription(self, *, subscription_id):
        self.canceled.append(subscription_id)


@pytest.fixture(autouse=True)
def _patch_provider(monkeypatch):
    provider = _FakeProvider()
    monkeypatch.setattr(billing_service, "get_billing_provider", lambda: provider)
    yield provider


# -- get_or_create_subscription ---------------------------------------------
def test_get_or_create_subscription_creates_free_row_if_missing():
    cid = uuid.uuid4()
    session = FakeSession(results=[FakeResult(scalar=None)])
    sub = billing_service.get_or_create_subscription(session, cid)
    assert sub.plan == PlanTier.free
    assert sub.status == SubscriptionStatus.active
    assert len(session.added_of(Subscription)) == 1
    assert session.commits == 1


def test_get_or_create_subscription_returns_existing():
    cid = uuid.uuid4()
    existing = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.pro,
                            status=SubscriptionStatus.active)
    session = FakeSession(results=[FakeResult(scalar=existing)])
    sub = billing_service.get_or_create_subscription(session, cid)
    assert sub is existing
    assert session.commits == 0


# -- get_usage ----------------------------------------------------------------
def test_get_usage_counts_real_rows_against_plan_limits():
    cid = uuid.uuid4()
    sub = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.free,
                       status=SubscriptionStatus.active)
    session = FakeSession(results=[
        FakeResult(scalar=sub),                       # get_or_create_subscription
        FakeResult(scalars=list(range(7))),           # document count
        FakeResult(scalars=list(range(2))),           # analysis job count
        FakeResult(scalars=list(range(1))),           # active project count
    ])
    usage = billing_service.get_usage(session, cid)
    assert usage["plan"] == "free"
    assert usage["documents_processed"] == 7
    assert usage["documents_limit"] == 20
    assert usage["analysis_runs"] == 2
    assert usage["analysis_runs_limit"] == 5
    assert usage["projects_active"] == 1
    assert usage["projects_limit"] == 1


# -- start_checkout ------------------------------------------------------------
def test_start_checkout_raises_when_plan_not_configured():
    cid = uuid.uuid4()
    actor = User(id=uuid.uuid4(), email="admin@example.com", password_hash="x", is_active=True)
    sub = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.free,
                       status=SubscriptionStatus.active)
    session = FakeSession(results=[FakeResult(scalar=sub)])
    with pytest.raises(billing_service.PlanNotConfigured):
        billing_service.start_checkout(session, cid, actor, PlanTier.pro)


def test_start_checkout_rejects_free_plan():
    cid = uuid.uuid4()
    actor = User(id=uuid.uuid4(), email="admin@example.com", password_hash="x", is_active=True)
    session = FakeSession()
    with pytest.raises(ValueError):
        billing_service.start_checkout(session, cid, actor, PlanTier.free)


def test_start_checkout_blocks_a_second_subscription_for_an_already_paid_org(monkeypatch):
    """Checkout Sessions in subscription mode always create a NEW Stripe
    subscription — an org that already has one active must be blocked from
    starting a second, or they'd end up with two concurrent subscriptions
    (and two concurrent charges)."""
    from app.config import get_settings
    monkeypatch.setenv("VA_STRIPE_PRICE_ENTERPRISE", "price_enterprise_123")
    get_settings.cache_clear()

    cid = uuid.uuid4()
    actor = User(id=uuid.uuid4(), email="admin@example.com", password_hash="x", is_active=True)
    sub = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.pro,
                       status=SubscriptionStatus.active, stripe_customer_id="cus_existing",
                       stripe_subscription_id="sub_existing")
    session = FakeSession(results=[FakeResult(scalar=sub)])

    with pytest.raises(billing_service.AlreadyOnPaidPlan):
        billing_service.start_checkout(session, cid, actor, PlanTier.enterprise)
    get_settings.cache_clear()


def test_checkout_endpoint_409_when_already_on_paid_plan(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("VA_STRIPE_PRICE_ENTERPRISE", "price_enterprise_123")
    get_settings.cache_clear()

    user = User(id=uuid.uuid4(), email="admin@example.com", password_hash="x", is_active=True)
    cid = uuid.uuid4()
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid, role=MembershipRole.admin)
    sub = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.pro,
                       status=SubscriptionStatus.active, stripe_customer_id="cus_existing",
                       stripe_subscription_id="sub_existing")
    session = FakeSession(results=[FakeResult(scalar=membership), FakeResult(scalar=sub)])
    resp = _client(session, user).post(f"/orgs/{cid}/billing/checkout", json={"plan": "enterprise"})
    assert resp.status_code == 409
    assert "already" in resp.json()["detail"].lower()
    get_settings.cache_clear()


def test_start_checkout_creates_customer_and_returns_url(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("VA_STRIPE_PRICE_PRO", "price_pro_123")
    get_settings.cache_clear()

    cid = uuid.uuid4()
    actor = User(id=uuid.uuid4(), email="admin@example.com", password_hash="x", is_active=True)
    sub = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.free,
                       status=SubscriptionStatus.active, stripe_customer_id=None)
    org = Organization(id=cid, name="Acme Co")
    session = FakeSession(results=[FakeResult(scalar=sub)], get_obj=org)

    result = billing_service.start_checkout(session, cid, actor, PlanTier.pro)
    assert result.url.startswith("https://checkout.stripe.com/fake")
    assert sub.stripe_customer_id == "cus_fake123"
    get_settings.cache_clear()


def test_start_checkout_passes_a_scoped_idempotency_key(monkeypatch, _patch_provider):
    """A double-click/retry within the same short window must reuse one
    Stripe Checkout Session rather than minting a second one."""
    from app.config import get_settings
    monkeypatch.setenv("VA_STRIPE_PRICE_PRO", "price_pro_123")
    get_settings.cache_clear()

    cid = uuid.uuid4()
    actor = User(id=uuid.uuid4(), email="admin@example.com", password_hash="x", is_active=True)
    sub = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.free,
                       status=SubscriptionStatus.active, stripe_customer_id="cus_existing")
    session = FakeSession(results=[FakeResult(scalar=sub)])

    billing_service.start_checkout(session, cid, actor, PlanTier.pro)
    key = _patch_provider.last_idempotency_key
    assert key is not None
    assert key.startswith(f"checkout-{cid}-pro-")
    get_settings.cache_clear()


# -- start_billing_portal -------------------------------------------------------
def test_start_billing_portal_requires_existing_customer():
    cid = uuid.uuid4()
    actor = User(id=uuid.uuid4(), email="admin@example.com", password_hash="x", is_active=True)
    sub = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.free,
                       status=SubscriptionStatus.active, stripe_customer_id=None)
    session = FakeSession(results=[FakeResult(scalar=sub)])
    with pytest.raises(BillingNotConfigured):
        billing_service.start_billing_portal(session, cid, actor)


def test_start_billing_portal_returns_url_when_customer_exists():
    cid = uuid.uuid4()
    actor = User(id=uuid.uuid4(), email="admin@example.com", password_hash="x", is_active=True)
    sub = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.pro,
                       status=SubscriptionStatus.active, stripe_customer_id="cus_existing")
    session = FakeSession(results=[FakeResult(scalar=sub)])
    result = billing_service.start_billing_portal(session, cid, actor)
    assert result.url == "https://billing.stripe.com/fake-portal"


# -- cancel_subscription --------------------------------------------------------
def test_cancel_subscription_rejects_free_plan():
    cid = uuid.uuid4()
    actor = User(id=uuid.uuid4(), email="admin@example.com", password_hash="x", is_active=True)
    sub = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.free,
                       status=SubscriptionStatus.active)
    session = FakeSession(results=[FakeResult(scalar=sub)])
    with pytest.raises(billing_service.NoActiveSubscription):
        billing_service.cancel_subscription(session, cid, actor)


def test_cancel_subscription_sets_flag_and_calls_provider(_patch_provider):
    cid = uuid.uuid4()
    actor = User(id=uuid.uuid4(), email="admin@example.com", password_hash="x", is_active=True)
    sub = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.pro,
                       status=SubscriptionStatus.active, stripe_subscription_id="sub_123")
    session = FakeSession(results=[FakeResult(scalar=sub)])
    result = billing_service.cancel_subscription(session, cid, actor)
    assert result.cancel_at_period_end is True
    assert "sub_123" in _patch_provider.canceled
    assert len(session.added_of(__import__("app.models", fromlist=["AuditLog"]).AuditLog)) == 1


# -- webhook handling ------------------------------------------------------------
def test_webhook_checkout_completed_links_customer_and_subscription():
    cid = uuid.uuid4()
    sub = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.free,
                       status=SubscriptionStatus.active)
    session = FakeSession(results=[FakeResult(scalar=sub)])
    event = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "client_reference_id": str(cid), "customer": "cus_abc", "subscription": "sub_abc",
        }},
    }
    billing_service.handle_webhook_event(session, event)
    assert sub.stripe_customer_id == "cus_abc"
    assert sub.stripe_subscription_id == "sub_abc"


def test_webhook_subscription_updated_applies_plan_and_period(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("VA_STRIPE_PRICE_PRO", "price_pro_123")
    get_settings.cache_clear()

    cid = uuid.uuid4()
    sub = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.free,
                       status=SubscriptionStatus.active, stripe_subscription_id="sub_abc")
    session = FakeSession(results=[FakeResult(scalar=sub)])
    period_end_ts = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp())
    event = {
        "type": "customer.subscription.updated",
        "data": {"object": {
            "id": "sub_abc", "status": "active", "current_period_end": period_end_ts,
            "cancel_at_period_end": False,
            "items": {"data": [{"price": {"id": "price_pro_123"}}]},
        }},
    }
    billing_service.handle_webhook_event(session, event)
    assert sub.plan == PlanTier.pro
    assert sub.status == SubscriptionStatus.active
    assert sub.current_period_end.year == 2026
    get_settings.cache_clear()


def test_webhook_subscription_deleted_downgrades_to_free():
    sub = Subscription(id=uuid.uuid4(), company_id=uuid.uuid4(), plan=PlanTier.pro,
                       status=SubscriptionStatus.active, stripe_subscription_id="sub_abc")
    session = FakeSession(results=[FakeResult(scalar=sub)])
    event = {"type": "customer.subscription.deleted", "data": {"object": {"id": "sub_abc"}}}
    billing_service.handle_webhook_event(session, event)
    assert sub.plan == PlanTier.free
    assert sub.status == SubscriptionStatus.canceled


def test_webhook_invoice_paid_creates_invoice_row_once():
    cid = uuid.uuid4()
    sub = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.pro,
                       status=SubscriptionStatus.active, stripe_subscription_id="sub_abc")
    session = FakeSession(results=[
        FakeResult(scalar=None),   # dedup check: not already recorded
        FakeResult(scalar=sub),    # lookup subscription by stripe id
    ])
    event = {
        "type": "invoice.paid",
        "data": {"object": {
            "id": "in_123", "subscription": "sub_abc", "amount_paid": 4900, "currency": "aud",
            "period_start": int(datetime(2026, 7, 1, tzinfo=timezone.utc).timestamp()),
            "period_end": int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp()),
            "hosted_invoice_url": "https://stripe.example/invoice/in_123",
        }},
    }
    billing_service.handle_webhook_event(session, event)
    added = session.added_of(Invoice)
    assert len(added) == 1
    assert added[0].amount == Decimal("49")
    assert added[0].stripe_invoice_id == "in_123"


def test_webhook_malformed_event_raises_instead_of_marking_processed():
    """If applying the event raises partway through (malformed/incomplete
    Stripe payload — missing period_start here), handle_webhook_event must
    propagate the exception (so Stripe sees a 500 and retries) rather than
    swallowing it — swallowing it would leave the StripeEvent reservation
    committed, and a Stripe retry would then hit the "already recorded"
    short-circuit and silently never reprocess the event."""
    cid = uuid.uuid4()
    sub = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.pro,
                       status=SubscriptionStatus.active, stripe_subscription_id="sub_abc")
    session = FakeSession(
        results=[FakeResult(scalar=None), FakeResult(scalar=sub)],
        get_obj=None,
    )
    event = {
        "id": "evt_malformed", "type": "invoice.paid",
        "data": {"object": {
            "id": "in_bad", "subscription": "sub_abc", "amount_paid": 4900, "currency": "aud",
            # period_start/period_end deliberately missing
        }},
    }
    with pytest.raises(KeyError):
        billing_service.handle_webhook_event(session, event)
    # The reservation must not have been committed — only flushed — so a
    # retry of the same event_id would reprocess rather than no-op.
    assert session.commits == 0


def test_webhook_invoice_paid_is_idempotent_on_retry():
    session = FakeSession(results=[FakeResult(scalar=Invoice(
        id=uuid.uuid4(), company_id=uuid.uuid4(), plan=PlanTier.pro, amount=Decimal("49"),
        status=InvoiceStatus.paid, period_start=datetime.now(timezone.utc),
        period_end=datetime.now(timezone.utc), stripe_invoice_id="in_123",
    ))])
    event = {"type": "invoice.paid", "data": {"object": {"id": "in_123", "subscription": "sub_abc"}}}
    billing_service.handle_webhook_event(session, event)
    assert session.added == []  # already recorded — no duplicate insert, no extra query


# -- endpoints / RBAC ------------------------------------------------------------
def _client(session, user):
    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_get_subscription_forbidden_for_member():
    user = User(id=uuid.uuid4(), email="member@example.com", password_hash="x", is_active=True)
    cid = uuid.uuid4()
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid, role=MembershipRole.member)
    session = FakeSession(results=[FakeResult(scalar=membership)])
    resp = _client(session, user).get(f"/orgs/{cid}/billing/subscription")
    assert resp.status_code == 403


def test_get_subscription_ok_for_admin():
    user = User(id=uuid.uuid4(), email="admin@example.com", password_hash="x", is_active=True)
    cid = uuid.uuid4()
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid, role=MembershipRole.admin)
    sub = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.free,
                       status=SubscriptionStatus.active, cancel_at_period_end=False)
    session = FakeSession(results=[FakeResult(scalar=membership), FakeResult(scalar=sub)])
    resp = _client(session, user).get(f"/orgs/{cid}/billing/subscription")
    assert resp.status_code == 200
    assert resp.json()["plan"] == "free"


def test_get_subscription_forbidden_for_non_member_of_other_org():
    """Cross-tenant guard: admin of org A cannot read billing for org B."""
    user = User(id=uuid.uuid4(), email="admin@example.com", password_hash="x", is_active=True)
    other_company_id = uuid.uuid4()
    session = FakeSession(results=[FakeResult(scalar=None)])  # no membership row for other org
    resp = _client(session, user).get(f"/orgs/{other_company_id}/billing/subscription")
    assert resp.status_code == 403


def test_cancel_endpoint_returns_409_when_already_free():
    user = User(id=uuid.uuid4(), email="admin@example.com", password_hash="x", is_active=True)
    cid = uuid.uuid4()
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid, role=MembershipRole.admin)
    sub = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.free,
                       status=SubscriptionStatus.active)
    session = FakeSession(results=[FakeResult(scalar=membership), FakeResult(scalar=sub)])
    resp = _client(session, user).post(f"/orgs/{cid}/billing/cancel")
    assert resp.status_code == 409


def test_checkout_endpoint_409_when_plan_not_configured():
    user = User(id=uuid.uuid4(), email="admin@example.com", password_hash="x", is_active=True)
    cid = uuid.uuid4()
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid, role=MembershipRole.admin)
    sub = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.free,
                       status=SubscriptionStatus.active)
    session = FakeSession(results=[FakeResult(scalar=membership), FakeResult(scalar=sub)])
    resp = _client(session, user).post(f"/orgs/{cid}/billing/checkout", json={"plan": "pro"})
    assert resp.status_code == 409
