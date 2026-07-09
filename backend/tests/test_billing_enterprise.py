"""Enterprise billing (.24): webhook idempotency, plan-limit enforcement,
grace period, seat-based billing, feature flags, billing audit trail, RBAC.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.auth.deps import get_current_user, get_db, require_admin
from app.main import app
from app.models import (
    AuditLog,
    Invoice,
    InvoiceStatus,
    Membership,
    MembershipRole,
    PlanTier,
    StripeEvent,
    Subscription,
    SubscriptionStatus,
    User,
)
from app.services import billing as billing_service
from tests.fakes import FakeResult, FakeSession


class _FakeProvider:
    def resume_subscription(self, *, subscription_id):
        pass


@pytest.fixture(autouse=True)
def _patch_provider(monkeypatch):
    monkeypatch.setattr(billing_service, "get_billing_provider", lambda: _FakeProvider())


def _now():
    return datetime.now(timezone.utc)


def _sub(cid, plan=PlanTier.free, status=SubscriptionStatus.active, **kw):
    return Subscription(id=uuid.uuid4(), company_id=cid, plan=plan, status=status,
                       cancel_at_period_end=kw.pop("cancel_at_period_end", False), **kw)


# ============================================================================
# Webhook idempotency
# ============================================================================
class _RaceSession(FakeSession):
    """Simulates a concurrent duplicate webhook delivery winning the race:
    the dedup lookup says "not seen yet" for both requests, but the second
    request's reservation hits the stripe_events unique-key violation when
    flushed (the reservation is flushed — taking the row lock — before the
    event is actually applied; see handle_webhook_event's docstring)."""

    def __init__(self, *, results=None):
        super().__init__(results=results, get_obj=None)
        self._raise_next_flush = True

    def flush(self):
        self.flushes += 1
        if self._raise_next_flush:
            self._raise_next_flush = False
            raise IntegrityError("insert", {}, Exception("duplicate key value violates unique constraint"))


def test_webhook_new_event_is_processed():
    cid = uuid.uuid4()
    sub = _sub(cid, plan=PlanTier.pro, stripe_subscription_id="sub_abc")
    session = FakeSession(
        results=[FakeResult(scalar=None), FakeResult(scalar=sub)],  # invoice dedup=None, sub lookup
        get_obj=None,  # StripeEvent lookup: not seen before
    )
    event = {
        "id": "evt_1", "type": "invoice.paid",
        "data": {"object": {
            "id": "in_1", "subscription": "sub_abc", "amount_paid": 4900, "currency": "aud",
            "period_start": int(_now().timestamp()), "period_end": int(_now().timestamp()),
        }},
    }
    billing_service.handle_webhook_event(session, event)
    assert len(session.added_of(StripeEvent)) == 1
    assert len(session.added_of(Invoice)) == 1


def test_webhook_duplicate_event_already_recorded_is_ignored():
    cid = uuid.uuid4()
    existing_event = StripeEvent(id="evt_1", event_type="invoice.paid")
    session = FakeSession(get_obj=existing_event)  # StripeEvent lookup: already processed
    event = {"id": "evt_1", "type": "invoice.paid", "data": {"object": {"id": "in_1"}}}
    billing_service.handle_webhook_event(session, event)
    # No further processing at all — no queries, no new rows.
    assert session.added == []
    assert session.commits == 0


def test_webhook_concurrent_duplicate_caught_by_integrity_error():
    """Two requests both pass the "not seen yet" check at the same time;
    only one may actually record the event — the loser's commit fails with
    IntegrityError and must back off cleanly rather than double-apply."""
    session = _RaceSession(results=[FakeResult(scalar=None), FakeResult(scalar=None)])
    event = {"id": "evt_1", "type": "invoice.paid", "data": {"object": {"id": "in_1", "subscription": "sub_abc"}}}
    billing_service.handle_webhook_event(session, event)
    assert len(session.added_of(StripeEvent)) == 1  # attempted, but the commit "failed"
    assert session.added_of(Invoice) == []          # event body never applied


def test_webhook_missing_event_id_still_processes_but_skips_dedup():
    """Defensive: an event with no id (shouldn't happen with real Stripe, but
    malformed input must not crash) still gets applied — just without the
    idempotency guard, matching the pre-.24 behaviour for such input."""
    cid = uuid.uuid4()
    sub = _sub(cid)
    session = FakeSession(results=[FakeResult(scalar=None)])
    event = {"type": "customer.subscription.deleted", "data": {"object": {"id": "sub_missing"}}}
    billing_service.handle_webhook_event(session, event)  # sub lookup returns None -> no-op, no crash


# ============================================================================
# Plan-limit enforcement
# ============================================================================
def test_enforce_document_limit_under_limit_passes():
    cid = uuid.uuid4()
    session = FakeSession(results=[
        FakeResult(scalar=_sub(cid, plan=PlanTier.free)),
        FakeResult(scalars=list(range(5))),   # 5 documents so far this month
    ])
    billing_service.enforce_document_limit(session, cid, additional=1)  # 6 <= 20, fine


def test_enforce_document_limit_over_limit_raises_with_code():
    cid = uuid.uuid4()
    session = FakeSession(results=[
        FakeResult(scalar=_sub(cid, plan=PlanTier.free)),
        FakeResult(scalars=list(range(20))),  # already at the Free cap
    ])
    with pytest.raises(billing_service.PlanLimitExceeded) as ei:
        billing_service.enforce_document_limit(session, cid, additional=1)
    assert ei.value.code == "document_limit_exceeded"


def test_enforce_document_limit_unlimited_plan_never_raises():
    cid = uuid.uuid4()
    session = FakeSession(results=[FakeResult(scalar=_sub(cid, plan=PlanTier.enterprise))])
    billing_service.enforce_document_limit(session, cid, additional=10_000)


def test_enforce_analysis_limit_over_limit_raises():
    cid = uuid.uuid4()
    session = FakeSession(results=[
        FakeResult(scalar=_sub(cid, plan=PlanTier.free)),
        FakeResult(scalars=list(range(5))),  # already at the Free cap of 5/month
    ])
    with pytest.raises(billing_service.PlanLimitExceeded) as ei:
        billing_service.enforce_analysis_limit(session, cid)
    assert ei.value.code == "analysis_limit_exceeded"


def test_enforce_storage_limit_over_limit_raises():
    cid = uuid.uuid4()
    free_limit_bytes = 500 * 1024 * 1024
    session = FakeSession(results=[
        FakeResult(scalar=_sub(cid, plan=PlanTier.free)),
        # storage_bytes_used() is ONE combined execute (doc blobs + project
        # contract/scope text) → one scalar, nearly at the 500MB cap.
        FakeResult(scalar=free_limit_bytes - 100),
    ])
    with pytest.raises(billing_service.PlanLimitExceeded) as ei:
        billing_service.enforce_storage_limit(session, cid, additional_bytes=1_000)
    assert ei.value.code == "storage_limit_exceeded"


def test_storage_bytes_used_is_single_authoritative_calc():
    """storage_bytes_used is the one source of truth used by enforcement —
    it resolves to a single aggregated scalar (documents + project text),
    computed live so it needs no separate usage counter to keep in sync."""
    cid = uuid.uuid4()
    session = FakeSession(results=[FakeResult(scalar=1_234_567)])
    assert billing_service.storage_bytes_used(session, cid) == 1_234_567


def test_enforce_storage_limit_counts_project_text_toward_quota():
    """Regression for the review finding: contract/scope text persisted on
    Project rows must count toward the quota, not just Document blobs. Here
    the docs+text sum already exceeds Free's 500MB even with additional=0."""
    cid = uuid.uuid4()
    over = 500 * 1024 * 1024 + 1
    session = FakeSession(results=[
        FakeResult(scalar=_sub(cid, plan=PlanTier.free)),
        FakeResult(scalar=over),   # combined doc + contract/scope bytes
    ])
    with pytest.raises(billing_service.PlanLimitExceeded) as ei:
        billing_service.enforce_storage_limit(session, cid)
    assert ei.value.code == "storage_limit_exceeded"


def test_enforce_seat_limit_over_limit_raises():
    cid = uuid.uuid4()
    session = FakeSession(results=[
        FakeResult(scalar=_sub(cid, plan=PlanTier.free)),
        FakeResult(scalars=list(range(3))),  # already at the Free cap of 3 seats
    ])
    with pytest.raises(billing_service.PlanLimitExceeded) as ei:
        billing_service.enforce_seat_limit(session, cid)
    assert ei.value.code == "seat_limit_exceeded"


def test_enforce_seat_limit_respects_included_seats_override():
    cid = uuid.uuid4()
    sub = _sub(cid, plan=PlanTier.free, included_seats=10)  # negotiated override
    session = FakeSession(results=[
        FakeResult(scalar=sub),
        FakeResult(scalars=list(range(5))),
    ])
    billing_service.enforce_seat_limit(session, cid)  # 6 <= 10, fine despite Free's default of 3


def test_suspended_subscription_blocks_every_enforcement_check():
    cid = uuid.uuid4()
    suspended = _sub(cid, plan=PlanTier.pro, status=SubscriptionStatus.suspended)
    for fn, kwargs in [
        (billing_service.enforce_document_limit, {}),
        (billing_service.enforce_analysis_limit, {}),
        (billing_service.enforce_storage_limit, {}),
        (billing_service.enforce_seat_limit, {}),
    ]:
        session = FakeSession(results=[FakeResult(scalar=suspended)])
        with pytest.raises(billing_service.PlanLimitExceeded) as ei:
            fn(session, cid, **kwargs)
        assert ei.value.code == "subscription_suspended"


# ============================================================================
# Grace period
# ============================================================================
def test_grace_period_not_yet_expired_stays_past_due():
    cid = uuid.uuid4()
    sub = _sub(cid, plan=PlanTier.pro, status=SubscriptionStatus.past_due,
              grace_period_expires_at=_now() + timedelta(days=3))
    session = FakeSession(results=[FakeResult(scalar=sub)])
    result = billing_service.get_or_create_subscription(session, cid)
    assert result.status == SubscriptionStatus.past_due
    assert session.commits == 0


def test_grace_period_expired_flips_to_suspended():
    cid = uuid.uuid4()
    sub = _sub(cid, plan=PlanTier.pro, status=SubscriptionStatus.past_due,
              grace_period_expires_at=_now() - timedelta(hours=1))
    session = FakeSession(results=[FakeResult(scalar=sub)])
    result = billing_service.get_or_create_subscription(session, cid)
    assert result.status == SubscriptionStatus.suspended
    assert session.commits == 1
    assert any(a.action == "subscription.suspended" for a in session.added_of(AuditLog))


def test_webhook_payment_failed_starts_grace_period():
    cid = uuid.uuid4()
    sub = _sub(cid, plan=PlanTier.pro, stripe_subscription_id="sub_abc")
    session = FakeSession(results=[FakeResult(scalar=sub)])
    event = {"type": "invoice.payment_failed", "data": {"object": {"subscription": "sub_abc"}}}
    billing_service.handle_webhook_event(session, event)
    assert sub.status == SubscriptionStatus.past_due
    assert sub.grace_period_expires_at is not None
    assert any(a.action == "payment.failed" for a in session.added_of(AuditLog))


def test_webhook_payment_recovered_clears_grace_period_and_reactivates():
    cid = uuid.uuid4()
    sub = _sub(cid, plan=PlanTier.pro, status=SubscriptionStatus.past_due,
              stripe_subscription_id="sub_abc", grace_period_expires_at=_now() + timedelta(days=2))
    session = FakeSession(results=[FakeResult(scalar=None), FakeResult(scalar=sub)])
    event = {
        "type": "invoice.paid",
        "data": {"object": {
            "id": "in_recovered", "subscription": "sub_abc", "amount_paid": 4900, "currency": "aud",
            "period_start": int(_now().timestamp()), "period_end": int(_now().timestamp()),
        }},
    }
    billing_service.handle_webhook_event(session, event)
    assert sub.status == SubscriptionStatus.active
    assert sub.grace_period_expires_at is None
    assert any(a.action == "subscription.reactivated" for a in session.added_of(AuditLog))


def test_webhook_invoice_voided_marks_invoice():
    inv = Invoice(id=uuid.uuid4(), company_id=uuid.uuid4(), plan=PlanTier.pro, amount=Decimal("49"),
                 status=InvoiceStatus.paid, period_start=_now(), period_end=_now(),
                 stripe_invoice_id="in_1")
    session = FakeSession(results=[FakeResult(scalar=inv)])
    event = {"type": "invoice.voided", "data": {"object": {"id": "in_1"}}}
    billing_service.handle_webhook_event(session, event)
    assert inv.status == InvoiceStatus.void
    assert any(a.action == "invoice.voided" for a in session.added_of(AuditLog))


# ============================================================================
# Seats
# ============================================================================
def test_get_seats_free_plan():
    cid = uuid.uuid4()
    session = FakeSession(results=[
        FakeResult(scalar=_sub(cid, plan=PlanTier.free)),
        FakeResult(scalars=list(range(2))),
    ])
    seats = billing_service.get_seats(session, cid)
    assert seats == {"current_seats": 2, "included_seats": 3, "billable_seats": 0, "additional_seats": 0}


def test_get_seats_over_included_reports_billable():
    cid = uuid.uuid4()
    session = FakeSession(results=[
        FakeResult(scalar=_sub(cid, plan=PlanTier.pro)),
        FakeResult(scalars=list(range(20))),
    ])
    seats = billing_service.get_seats(session, cid)
    assert seats["included_seats"] == 15
    assert seats["billable_seats"] == 5


def test_get_seats_enterprise_unlimited():
    cid = uuid.uuid4()
    session = FakeSession(results=[
        FakeResult(scalar=_sub(cid, plan=PlanTier.enterprise)),
        FakeResult(scalars=list(range(500))),
    ])
    seats = billing_service.get_seats(session, cid)
    assert seats["included_seats"] is None
    assert seats["billable_seats"] == 0


# ============================================================================
# Seat overage billing (.25)
# ============================================================================
class _SeatOverageProvider:
    def __init__(self):
        self.synced = []

    def sync_seat_overage(self, *, subscription_id, price_id, quantity):
        self.synced.append((subscription_id, price_id, quantity))


def test_enforce_seat_limit_blocks_free_even_with_overage_configured(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("VA_STRIPE_PRICE_SEAT_OVERAGE", "price_seat_overage_123")
    get_settings.cache_clear()
    cid = uuid.uuid4()
    session = FakeSession(results=[
        FakeResult(scalar=_sub(cid, plan=PlanTier.free)),
        FakeResult(scalars=list(range(3))),
    ])
    with pytest.raises(billing_service.PlanLimitExceeded):
        billing_service.enforce_seat_limit(session, cid)
    get_settings.cache_clear()


def test_enforce_seat_limit_blocks_pro_without_overage_price_configured(monkeypatch):
    """No VA_STRIPE_PRICE_SEAT_OVERAGE set -> overage isn't billable yet, so
    the plan limit still hard-blocks (matches pre-.25 behaviour)."""
    monkeypatch.setenv("VA_STRIPE_PRICE_SEAT_OVERAGE", "")
    from app.config import get_settings
    get_settings.cache_clear()
    cid = uuid.uuid4()
    sub = _sub(cid, plan=PlanTier.pro, stripe_subscription_id="sub_abc")
    session = FakeSession(results=[
        FakeResult(scalar=sub),
        FakeResult(scalars=list(range(15))),
    ])
    try:
        with pytest.raises(billing_service.PlanLimitExceeded):
            billing_service.enforce_seat_limit(session, cid)
    finally:
        get_settings.cache_clear()


def test_enforce_seat_limit_allows_overage_for_paid_plan_with_live_subscription(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("VA_STRIPE_PRICE_SEAT_OVERAGE", "price_seat_overage_123")
    get_settings.cache_clear()
    cid = uuid.uuid4()
    sub = _sub(cid, plan=PlanTier.pro, stripe_subscription_id="sub_abc")
    session = FakeSession(results=[
        FakeResult(scalar=sub),
        FakeResult(scalars=list(range(15))),  # already at the 15-seat included cap
    ])
    billing_service.enforce_seat_limit(session, cid)  # 16th seat allowed through as overage
    get_settings.cache_clear()


def test_get_seats_syncs_overage_quantity_to_stripe(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("VA_STRIPE_PRICE_SEAT_OVERAGE", "price_seat_overage_123")
    get_settings.cache_clear()
    provider = _SeatOverageProvider()
    monkeypatch.setattr(billing_service, "get_billing_provider", lambda: provider)

    cid = uuid.uuid4()
    sub = _sub(cid, plan=PlanTier.pro, stripe_subscription_id="sub_abc")
    session = FakeSession(results=[
        FakeResult(scalar=sub),
        FakeResult(scalars=list(range(20))),  # 5 seats over the 15 included
    ])
    seats = billing_service.get_seats(session, cid)
    assert seats["billable_seats"] == 5
    assert provider.synced == [("sub_abc", "price_seat_overage_123", 5)]
    get_settings.cache_clear()


def test_get_seats_overage_sync_failure_does_not_break_the_view(monkeypatch):
    """A transient Stripe error while syncing overage must not turn a
    read-only seats view into a 500."""
    from app.config import get_settings
    monkeypatch.setenv("VA_STRIPE_PRICE_SEAT_OVERAGE", "price_seat_overage_123")
    get_settings.cache_clear()

    class _FailingProvider:
        def sync_seat_overage(self, **kwargs):
            raise RuntimeError("stripe unreachable")

    monkeypatch.setattr(billing_service, "get_billing_provider", lambda: _FailingProvider())

    cid = uuid.uuid4()
    sub = _sub(cid, plan=PlanTier.pro, stripe_subscription_id="sub_abc")
    session = FakeSession(results=[
        FakeResult(scalar=sub),
        FakeResult(scalars=list(range(20))),
    ])
    seats = billing_service.get_seats(session, cid)  # must not raise
    assert seats["billable_seats"] == 5
    get_settings.cache_clear()


# ============================================================================
# Project limit (.25)
# ============================================================================
def test_enforce_project_limit_free_over_cap_raises():
    cid = uuid.uuid4()
    session = FakeSession(results=[
        FakeResult(scalar=_sub(cid, plan=PlanTier.free)),
        FakeResult(scalars=list(range(1))),  # already at Free's 1-project cap
    ])
    with pytest.raises(billing_service.PlanLimitExceeded) as ei:
        billing_service.enforce_project_limit(session, cid)
    assert ei.value.code == "project_limit_exceeded"


def test_enforce_project_limit_pro_under_cap_passes():
    cid = uuid.uuid4()
    session = FakeSession(results=[
        FakeResult(scalar=_sub(cid, plan=PlanTier.pro)),
        FakeResult(scalars=list(range(24))),
    ])
    billing_service.enforce_project_limit(session, cid)  # 25 <= 25, fine


def test_enforce_project_limit_enterprise_unlimited():
    cid = uuid.uuid4()
    session = FakeSession(results=[FakeResult(scalar=_sub(cid, plan=PlanTier.enterprise))])
    billing_service.enforce_project_limit(session, cid, additional=10_000)


# ============================================================================
# Monthly/annual checkout (.25)
# ============================================================================
def test_start_checkout_selects_annual_price(monkeypatch):
    from app.billing.provider import CheckoutSession
    from app.config import get_settings
    monkeypatch.setenv("VA_STRIPE_PRICE_PRO", "price_pro_monthly")
    monkeypatch.setenv("VA_STRIPE_PRICE_PRO_ANNUAL", "price_pro_annual")
    get_settings.cache_clear()

    class _CheckoutProvider:
        def create_checkout_session(self, *, customer_id, price_id, success_url, cancel_url,
                                    client_reference_id, idempotency_key=None):
            return CheckoutSession(url=f"https://checkout.stripe.com/fake?price={price_id}")

    monkeypatch.setattr(billing_service, "get_billing_provider", lambda: _CheckoutProvider())

    cid = uuid.uuid4()
    actor = User(id=uuid.uuid4(), email="admin@example.com", password_hash="x", is_active=True)
    sub = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.free,
                       status=SubscriptionStatus.active, stripe_customer_id="cus_existing")
    session = FakeSession(results=[FakeResult(scalar=sub)])

    result = billing_service.start_checkout(session, cid, actor, PlanTier.pro, "annual")
    assert "price_pro_annual" in result.url
    get_settings.cache_clear()


def test_start_checkout_annual_not_configured_raises(monkeypatch):
    monkeypatch.setenv("VA_STRIPE_PRICE_PRO_ANNUAL", "")
    from app.config import get_settings
    get_settings.cache_clear()
    cid = uuid.uuid4()
    actor = User(id=uuid.uuid4(), email="admin@example.com", password_hash="x", is_active=True)
    sub = Subscription(id=uuid.uuid4(), company_id=cid, plan=PlanTier.free,
                       status=SubscriptionStatus.active)
    session = FakeSession(results=[FakeResult(scalar=sub)])
    try:
        with pytest.raises(billing_service.PlanNotConfigured):
            billing_service.start_checkout(session, cid, actor, PlanTier.pro, "annual")
    finally:
        get_settings.cache_clear()


# ============================================================================
# Feature gating (.25)
# ============================================================================
def test_enforce_feature_raises_for_disabled_feature():
    cid = uuid.uuid4()
    session = FakeSession(results=[FakeResult(scalar=_sub(cid, plan=PlanTier.free))])
    with pytest.raises(billing_service.FeatureNotAvailable) as ei:
        billing_service.enforce_feature(session, cid, "exports")
    assert ei.value.feature == "exports"


def test_enforce_feature_passes_for_enabled_feature():
    cid = uuid.uuid4()
    session = FakeSession(results=[FakeResult(scalar=_sub(cid, plan=PlanTier.pro))])
    billing_service.enforce_feature(session, cid, "exports")  # no raise


# ============================================================================
# Feature flags
# ============================================================================
@pytest.mark.parametrize("plan,expected", [
    (PlanTier.free, {"audit_log": False, "exports": False, "sso": False,
                    "priority_support": False, "advanced_analytics": False}),
    (PlanTier.pro, {"audit_log": True, "exports": True, "sso": False,
                   "priority_support": False, "advanced_analytics": False}),
    (PlanTier.enterprise, {"audit_log": True, "exports": True, "sso": True,
                          "priority_support": True, "advanced_analytics": True}),
])
def test_get_features_matches_plan(plan, expected):
    cid = uuid.uuid4()
    session = FakeSession(results=[FakeResult(scalar=_sub(cid, plan=plan))])
    assert billing_service.get_features(session, cid) == expected


# ============================================================================
# Resume subscription
# ============================================================================
def test_resume_requires_pending_cancellation():
    cid = uuid.uuid4()
    session = FakeSession(results=[FakeResult(scalar=_sub(cid, plan=PlanTier.pro))])
    with pytest.raises(billing_service.NoActiveSubscription):
        billing_service.resume_subscription(session, cid, User(id=uuid.uuid4(), email="a@b.com"))


def test_resume_clears_cancel_flag_and_audits():
    cid = uuid.uuid4()
    sub = _sub(cid, plan=PlanTier.pro, cancel_at_period_end=True, stripe_subscription_id="sub_abc")
    session = FakeSession(results=[FakeResult(scalar=sub)])
    actor = User(id=uuid.uuid4(), email="admin@example.com")
    result = billing_service.resume_subscription(session, cid, actor)
    assert result.cancel_at_period_end is False
    assert any(a.action == "subscription.reactivated" for a in session.added_of(AuditLog))


# ============================================================================
# Endpoint authorization + multi-tenant isolation
# ============================================================================
def _client(session, user):
    def _db():
        yield session
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


@pytest.mark.parametrize("method,path_suffix,body", [
    ("get", "/seats", None),
    ("get", "/features", None),
    ("get", "/audit", None),
    ("post", "/resume", None),
])
def test_new_billing_endpoints_forbidden_for_member(method, path_suffix, body):
    user = User(id=uuid.uuid4(), email="member@example.com", password_hash="x", is_active=True)
    cid = uuid.uuid4()
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid, role=MembershipRole.member)
    session = FakeSession(results=[FakeResult(scalar=membership)])
    client = _client(session, user)
    resp = getattr(client, method)(f"/orgs/{cid}/billing{path_suffix}", json=body) if method == "post" \
        else client.get(f"/orgs/{cid}/billing{path_suffix}")
    assert resp.status_code == 403


def test_seats_endpoint_ok_for_admin():
    user = User(id=uuid.uuid4(), email="admin@example.com", password_hash="x", is_active=True)
    cid = uuid.uuid4()
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid, role=MembershipRole.admin)
    session = FakeSession(results=[
        FakeResult(scalar=membership),
        FakeResult(scalar=_sub(cid, plan=PlanTier.free)),
        FakeResult(scalars=[membership]),
    ])
    resp = _client(session, user).get(f"/orgs/{cid}/billing/seats")
    assert resp.status_code == 200
    assert resp.json()["included_seats"] == 3


def test_features_endpoint_ok_for_admin():
    user = User(id=uuid.uuid4(), email="admin@example.com", password_hash="x", is_active=True)
    cid = uuid.uuid4()
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid, role=MembershipRole.admin)
    session = FakeSession(results=[
        FakeResult(scalar=membership),
        FakeResult(scalar=_sub(cid, plan=PlanTier.enterprise)),
    ])
    resp = _client(session, user).get(f"/orgs/{cid}/billing/features")
    assert resp.status_code == 200
    assert resp.json()["sso"] is True


def test_billing_audit_endpoint_ok_for_admin():
    user = User(id=uuid.uuid4(), email="admin@example.com", password_hash="x", is_active=True)
    cid = uuid.uuid4()
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid, role=MembershipRole.admin)
    entry = AuditLog(id=uuid.uuid4(), company_id=cid, actor_user_id=None,
                     entity_type="subscription", entity_id=cid,
                     action="payment.succeeded", after={"amount": "49"})
    session = FakeSession(results=[FakeResult(scalar=membership), FakeResult(scalars=[entry])])
    resp = _client(session, user).get(f"/orgs/{cid}/billing/audit")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1 and body[0]["action"] == "payment.succeeded"


def test_billing_endpoints_cross_tenant_forbidden():
    """Admin of org A must not be able to read org B's billing state."""
    user = User(id=uuid.uuid4(), email="admin@example.com", password_hash="x", is_active=True)
    other_company_id = uuid.uuid4()
    session = FakeSession(results=[FakeResult(scalar=None)])  # no membership row for the other org
    resp = _client(session, user).get(f"/orgs/{other_company_id}/billing/seats")
    assert resp.status_code == 403


def test_resume_endpoint_409_when_not_pending_cancellation():
    user = User(id=uuid.uuid4(), email="admin@example.com", password_hash="x", is_active=True)
    cid = uuid.uuid4()
    membership = Membership(id=uuid.uuid4(), user_id=user.id, company_id=cid, role=MembershipRole.admin)
    session = FakeSession(results=[
        FakeResult(scalar=membership),
        FakeResult(scalar=_sub(cid, plan=PlanTier.pro)),  # not pending cancellation
    ])
    resp = _client(session, user).post(f"/orgs/{cid}/billing/resume")
    assert resp.status_code == 409
