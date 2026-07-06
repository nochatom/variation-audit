"""Billing & subscriptions (.23, .24, .25).

Subscription rows are created lazily (Free/active) the first time an org's
billing page is viewed — no signup-flow change was needed. Usage numbers are
always real (counted from actual Document/AnalysisJob rows for the current
calendar month), never a separate fabricated counter.

.24 adds: server-side plan-limit enforcement, webhook idempotency (stripe_events
ledger), a billing audit trail (reuses the existing immutable audit_log table),
seat-based billing groundwork, a soft grace period on payment failure, and
plan feature flags.

.25 adds: the real published pricing (Free/Pro/Enterprise, AUD), a per-org
project-count limit, monthly/annual Stripe pricing, and seat-overage billing
for Pro/Enterprise orgs with a live Stripe subscription.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.billing.provider import BillingNotConfigured, get_billing_provider
from app.config import get_settings
from app.logging_config import security_logger
from app.models import (
    AnalysisJob,
    AuditLog,
    Document,
    Invoice,
    InvoiceStatus,
    Membership,
    Organization,
    PlanTier,
    Project,
    StripeEvent,
    Subscription,
    SubscriptionStatus,
    User,
)

BillingInterval = Literal["monthly", "annual"]

# Published pricing (.25) — Free / Pro (AUD 149/mo, AUD 1490/yr) / Enterprise
# (Contact Sales, custom, unlimited usage).
PLAN_LIMITS: dict[PlanTier, dict[str, int | None]] = {
    PlanTier.free: {
        "projects": 1, "documents_per_month": 20, "analysis_runs_per_month": 5,
        "seats": 3, "storage_mb": 500,
    },
    PlanTier.pro: {
        "projects": 25, "documents_per_month": 500, "analysis_runs_per_month": 100,
        "seats": 15, "storage_mb": 5_000,
    },
    PlanTier.enterprise: {
        "projects": None, "documents_per_month": None, "analysis_runs_per_month": None,
        "seats": None, "storage_mb": None,
    },
}

# Feature flags (.24) — the frontend consumes these via GET .../billing/features
# rather than hardcoding plan → capability logic of its own.
PLAN_FEATURES: dict[PlanTier, dict[str, bool]] = {
    PlanTier.free: {
        "audit_log": False, "exports": False, "sso": False,
        "priority_support": False, "advanced_analytics": False,
    },
    PlanTier.pro: {
        "audit_log": True, "exports": True, "sso": False,
        "priority_support": False, "advanced_analytics": False,
    },
    PlanTier.enterprise: {
        "audit_log": True, "exports": True, "sso": True,
        "priority_support": True, "advanced_analytics": True,
    },
}

_PLAN_RANK = {PlanTier.free: 0, PlanTier.pro: 1, PlanTier.enterprise: 2}


class PlanNotConfigured(Exception):
    """The requested plan has no live Stripe Price ID set yet — self-serve
    checkout can't be offered for it until product/pricing configures one."""


class AlreadyOnPaidPlan(Exception):
    """Checkout was requested for an org that already has an active paid
    Stripe subscription. Checkout Sessions in subscription mode always
    create a BRAND NEW subscription — letting this through would give the
    org two concurrent Stripe subscriptions (and two concurrent charges).
    Switching between paid tiers isn't wired up yet (see module docs); the
    safe default is to block it and point the admin at the billing portal."""


class NoActiveSubscription(Exception):
    """Cancel/resume was requested in a state where there's nothing to do
    (e.g. cancel on an org already on Free; resume on a subscription that
    isn't pending cancellation)."""


class PlanLimitExceeded(Exception):
    """A protected action would exceed the org's plan limit (or the account
    is suspended). `code` is machine-readable — routers map it straight onto
    the 402 response body's error_code field, so frontend callers can branch
    on it without parsing message text."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _month_start() -> datetime:
    return _now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _count_since(session: Session, model, company_id: uuid.UUID, since: datetime) -> int:
    return len(session.execute(
        select(model.id).where(model.company_id == company_id, model.created_at >= since)
    ).scalars().all())


def _seat_count(session: Session, company_id: uuid.UUID) -> int:
    return len(session.execute(
        select(Membership.id).where(Membership.company_id == company_id)
    ).scalars().all())


def _included_seats(sub: Subscription) -> int | None:
    """NULL on the row = use the plan default; set = a negotiated override
    (seat-based billing groundwork, .24) — not yet wired to a per-seat
    Stripe price."""
    if sub.included_seats is not None:
        return sub.included_seats
    return PLAN_LIMITS[sub.plan]["seats"]


# -- subscription lifecycle --------------------------------------------------
def get_or_create_subscription(session: Session, company_id: uuid.UUID) -> Subscription:
    sub = session.execute(
        select(Subscription).where(Subscription.company_id == company_id)
    ).scalar_one_or_none()
    if sub is None:
        sub = Subscription(id=uuid.uuid4(), company_id=company_id,
                           plan=PlanTier.free, status=SubscriptionStatus.active)
        session.add(sub)
        session.commit()
        return sub
    _apply_grace_period_expiry(session, sub)
    return sub


def _apply_grace_period_expiry(session: Session, sub: Subscription) -> None:
    """Lazy expiry check (same pattern as lazy Subscription creation above):
    evaluated whenever the subscription is read, rather than needing a
    background scheduler. A `past_due` subscription whose grace period has
    elapsed with no successful payment flips to `suspended`."""
    if sub.status != SubscriptionStatus.past_due or sub.grace_period_expires_at is None:
        return
    if sub.grace_period_expires_at >= _now():
        return
    sub.status = SubscriptionStatus.suspended
    _billing_audit(session, sub.company_id, None, "subscription.suspended",
                   {"plan": sub.plan.value, "reason": "grace_period_expired"})
    session.commit()


def get_usage(session: Session, company_id: uuid.UUID) -> dict:
    sub = get_or_create_subscription(session, company_id)
    since = _month_start()

    doc_count = _count_since(session, Document, company_id, since)
    job_count = _count_since(session, AnalysisJob, company_id, since)
    project_count = len(session.execute(
        select(Project.id).where(Project.company_id == company_id, Project.archived_at.is_(None))
    ).scalars().all())

    limits = PLAN_LIMITS[sub.plan]
    return {
        "plan": sub.plan.value,
        "period_start": since.isoformat(),
        "projects_active": project_count,
        "projects_limit": limits["projects"],
        "documents_processed": doc_count,
        "documents_limit": limits["documents_per_month"],
        "analysis_runs": job_count,
        "analysis_runs_limit": limits["analysis_runs_per_month"],
        "seats_limit": limits["seats"],
    }


def get_seats(session: Session, company_id: uuid.UUID) -> dict:
    """Seat-based billing groundwork (.24) — exposes current/included/billable
    seats even though no per-seat Stripe price is wired up yet."""
    sub = get_or_create_subscription(session, company_id)
    included = _included_seats(sub)
    current = _seat_count(session, company_id)
    billable = 0 if included is None else max(0, current - included)
    _sync_seat_overage(sub, billable)
    return {
        "current_seats": current,
        "included_seats": included,
        "billable_seats": billable,
        "additional_seats": billable,
    }


def get_features(session: Session, company_id: uuid.UUID) -> dict:
    """Plan capability flags (.24) — the frontend consumes this instead of
    hardcoding its own plan → feature logic."""
    sub = get_or_create_subscription(session, company_id)
    return dict(PLAN_FEATURES[sub.plan])


class FeatureNotAvailable(Exception):
    """Raised when a plan-gated feature (PDF export, audit log, ...) is used
    by an org whose plan doesn't include it (.25) — routers map this onto a
    403 rather than silently no-op'ing or 404'ing."""

    def __init__(self, feature: str):
        self.feature = feature
        super().__init__(f"the '{feature}' feature isn't available on your current plan — upgrade to access it")


def enforce_feature(session: Session, company_id: uuid.UUID, feature: str) -> None:
    """Real (not just display-only) feature gating (.25) — call before doing
    the actual protected work (rendering a PDF, returning audit rows)."""
    if not get_features(session, company_id).get(feature, False):
        raise FeatureNotAvailable(feature)


def start_checkout(session: Session, company_id: uuid.UUID, actor: User, plan: PlanTier,
                   billing_interval: BillingInterval = "monthly"):
    from app.billing.provider import CheckoutSession  # noqa: F401 (re-exported type for callers)

    if plan == PlanTier.free:
        raise ValueError("cannot checkout into the free plan")

    settings = get_settings()
    # Annual pricing (.25) is additive — only Pro has a self-serve annual
    # price today; Enterprise is Contact Sales regardless of interval, and a
    # plan/interval combination with no configured price is simply not
    # self-serve-purchasable yet (PlanNotConfigured), not a silent fallback
    # to monthly.
    price_id = {
        ("pro", "monthly"): settings.stripe_price_pro,
        ("pro", "annual"): settings.stripe_price_pro_annual,
        ("enterprise", "monthly"): settings.stripe_price_enterprise,
        ("enterprise", "annual"): settings.stripe_price_enterprise,
    }[(plan.value, billing_interval)]
    if not price_id:
        raise PlanNotConfigured(f"no Stripe price configured for plan '{plan.value}' ({billing_interval})")

    provider = get_billing_provider()
    sub = get_or_create_subscription(session, company_id)
    org = session.get(Organization, company_id)

    if sub.stripe_subscription_id and sub.plan != PlanTier.free:
        # Already has a live Stripe subscription — Checkout would create a
        # SECOND one (double billing) rather than change the existing plan.
        raise AlreadyOnPaidPlan(
            "your organization already has an active paid subscription — "
            "use \"Manage billing\" to change plans, or cancel your current plan first"
        )

    if sub.stripe_customer_id is None:
        sub.stripe_customer_id = provider.get_or_create_customer(
            company_id=str(company_id), email=actor.email, name=org.name if org else "Organization",
        )
        session.commit()

    base = settings.frontend_base_url.rstrip("/")
    # 30-second-bucketed idempotency key: a double-click or a client-side
    # retry within that window reuses the same Checkout Session instead of
    # creating a second one; a genuinely later attempt (next bucket) still
    # gets a fresh session rather than being stuck replaying a stale one.
    idempotency_key = f"checkout-{company_id}-{plan.value}-{billing_interval}-{int(time.time() // 30)}"
    result = provider.create_checkout_session(
        customer_id=sub.stripe_customer_id, price_id=price_id,
        success_url=f"{base}/app/settings/billing?checkout=success",
        cancel_url=f"{base}/app/settings/billing?checkout=cancelled",
        client_reference_id=str(company_id),
        idempotency_key=idempotency_key,
    )
    _billing_audit(session, company_id, actor.id, "subscription.checkout_started",
                   {"plan": plan.value, "billing_interval": billing_interval})
    session.commit()
    return result


def start_billing_portal(session: Session, company_id: uuid.UUID, actor: User):
    sub = get_or_create_subscription(session, company_id)
    if sub.stripe_customer_id is None:
        raise BillingNotConfigured("no billing account yet — upgrade to a paid plan first")

    provider = get_billing_provider()
    base = get_settings().frontend_base_url.rstrip("/")
    result = provider.create_billing_portal_session(
        customer_id=sub.stripe_customer_id, return_url=f"{base}/app/settings/billing",
    )
    _billing_audit(session, company_id, actor.id, "billing_portal.accessed", None)
    session.commit()
    return result


def cancel_subscription(session: Session, company_id: uuid.UUID, actor: User) -> Subscription:
    sub = get_or_create_subscription(session, company_id)
    if sub.plan == PlanTier.free:
        raise NoActiveSubscription("already on the free plan")

    if sub.stripe_subscription_id:
        provider = get_billing_provider()
        provider.cancel_subscription(subscription_id=sub.stripe_subscription_id)

    sub.cancel_at_period_end = True
    _billing_audit(session, company_id, actor.id, "subscription.cancel_requested",
                   {"plan": sub.plan.value, "current_period_end":
                    sub.current_period_end.isoformat() if sub.current_period_end else None})
    session.commit()
    return sub


def resume_subscription(session: Session, company_id: uuid.UUID, actor: User) -> Subscription:
    """Undo a pending cancel_at_period_end — the org keeps its current plan
    instead of dropping to Free at the end of the billing period."""
    sub = get_or_create_subscription(session, company_id)
    if not sub.cancel_at_period_end:
        raise NoActiveSubscription("subscription is not pending cancellation")

    if sub.stripe_subscription_id:
        provider = get_billing_provider()
        provider.resume_subscription(subscription_id=sub.stripe_subscription_id)

    sub.cancel_at_period_end = False
    _billing_audit(session, company_id, actor.id, "subscription.reactivated", {"plan": sub.plan.value})
    session.commit()
    return sub


def list_invoices(session: Session, company_id: uuid.UUID) -> list[Invoice]:
    return list(session.execute(
        select(Invoice).where(Invoice.company_id == company_id)
        .order_by(Invoice.created_at.desc())
    ).scalars().all())


# -- server-side plan-limit enforcement (.24) --------------------------------
# Every protected action calls one of these before doing real work. They
# raise PlanLimitExceeded (never return a falsy "not allowed" value) so a
# caller can't accidentally ignore the result — the router must either
# catch it and 402, or let it propagate.
def _check_not_suspended(sub: Subscription) -> None:
    if sub.status == SubscriptionStatus.suspended:
        raise PlanLimitExceeded(
            "subscription_suspended",
            "billing account suspended after a failed payment — update your payment method to restore access",
        )


def enforce_project_limit(session: Session, company_id: uuid.UUID, *, additional: int = 1) -> None:
    """Free is capped at 1 active project, Pro at 25, Enterprise unlimited
    (.25). Archived projects don't count — archiving is the intended way to
    free up a project slot without losing the underlying data."""
    sub = get_or_create_subscription(session, company_id)
    _check_not_suspended(sub)
    limit = PLAN_LIMITS[sub.plan]["projects"]
    if limit is None:
        return
    current = len(session.execute(
        select(Project.id).where(Project.company_id == company_id, Project.archived_at.is_(None))
    ).scalars().all())
    if current + additional > limit:
        raise PlanLimitExceeded("project_limit_exceeded",
                                f"plan limit of {limit} active projects reached")


def enforce_document_limit(session: Session, company_id: uuid.UUID, *, additional: int = 1) -> None:
    sub = get_or_create_subscription(session, company_id)
    _check_not_suspended(sub)
    limit = PLAN_LIMITS[sub.plan]["documents_per_month"]
    if limit is None:
        return
    current = _count_since(session, Document, company_id, _month_start())
    if current + additional > limit:
        raise PlanLimitExceeded("document_limit_exceeded",
                                f"plan limit of {limit} documents/month reached")


def enforce_analysis_limit(session: Session, company_id: uuid.UUID) -> None:
    sub = get_or_create_subscription(session, company_id)
    _check_not_suspended(sub)
    limit = PLAN_LIMITS[sub.plan]["analysis_runs_per_month"]
    if limit is None:
        return
    current = _count_since(session, AnalysisJob, company_id, _month_start())
    if current + 1 > limit:
        raise PlanLimitExceeded("analysis_limit_exceeded",
                                f"plan limit of {limit} analysis runs/month reached")


def enforce_storage_limit(session: Session, company_id: uuid.UUID, *, additional_bytes: int = 0) -> None:
    sub = get_or_create_subscription(session, company_id)
    _check_not_suspended(sub)
    limit_mb = PLAN_LIMITS[sub.plan]["storage_mb"]
    if limit_mb is None:
        return
    # Aggregated in SQL rather than fetching every Document row into Python:
    # unlike the monthly, plan-bounded counts above, this sums a company's
    # entire document history — unbounded and only growing, so it must not
    # scale with row count.
    total = session.execute(
        select(func.coalesce(func.sum(Document.size_bytes), 0)).where(Document.company_id == company_id)
    ).scalar_one() or 0
    total += additional_bytes
    if total > limit_mb * 1024 * 1024:
        raise PlanLimitExceeded("storage_limit_exceeded", f"plan storage limit of {limit_mb}MB reached")


def enforce_seat_limit(session: Session, company_id: uuid.UUID, *, additional: int = 1) -> None:
    sub = get_or_create_subscription(session, company_id)
    _check_not_suspended(sub)
    limit = _included_seats(sub)
    if limit is None:
        return
    current = _seat_count(session, company_id)
    if current + additional <= limit:
        return
    # Over the included-seat count. Free has no billing relationship to
    # charge overage against, so it stays hard-blocked. A paid plan with a
    # live Stripe subscription and a configured seat-overage price is let
    # through instead — the excess bills as overage (synced in get_seats())
    # rather than blocking the org from adding people.
    if _seat_overage_available(sub):
        return
    raise PlanLimitExceeded("seat_limit_exceeded", f"plan limit of {limit} seats reached")


def _seat_overage_available(sub: Subscription) -> bool:
    return (sub.plan != PlanTier.free and sub.stripe_subscription_id is not None
            and get_settings().stripe_price_seat_overage is not None)


def _sync_seat_overage(sub: Subscription, billable_seats: int) -> None:
    """Keeps the seat-overage Stripe subscription item's quantity in sync
    with the org's actual overage (.25). Best-effort: a transient Stripe
    error here must not break the (otherwise read-only) seats view."""
    if not _seat_overage_available(sub):
        return
    try:
        provider = get_billing_provider()
        provider.sync_seat_overage(
            subscription_id=sub.stripe_subscription_id,
            price_id=get_settings().stripe_price_seat_overage,
            quantity=billable_seats,
        )
    except Exception:
        security_logger.warning(
            "seat overage sync failed — billable seats may be stale in Stripe until the next sync",
            extra={"event": "seat_overage_sync_failed", "company_id": str(sub.company_id)},
        )


# -- Stripe webhook handling --------------------------------------------------
def _plan_from_price_id(price_id: str | None) -> PlanTier | None:
    if not price_id:
        return None
    settings = get_settings()
    if price_id in (settings.stripe_price_pro, settings.stripe_price_pro_annual):
        return PlanTier.pro
    if price_id == settings.stripe_price_enterprise:
        return PlanTier.enterprise
    return None


def _log_unrecognized_reference(event_type: str, stripe_id: str | None) -> None:
    """A webhook referenced a Stripe subscription/invoice id this app has no
    row for — always a legitimate no-op (Stripe sent it, there's nothing
    local to update), but silent no-ops here would make a real linkage bug
    (e.g. checkout.session.completed never landing) invisible in production."""
    security_logger.warning(
        "stripe webhook referenced an unknown local record — ignored",
        extra={"event": "stripe_webhook_unknown_reference",
               "stripe_event_type": event_type, "stripe_id": stripe_id},
    )


def _subscription_by_stripe_id(session: Session, stripe_subscription_id: str | None) -> Subscription | None:
    if not stripe_subscription_id:
        return None
    return session.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_subscription_id)
    ).scalar_one_or_none()


def handle_webhook_event(session: Session, event: dict) -> None:
    """Idempotency wrapper (.24): reserves `event["id"]` in stripe_events
    before applying it, but deliberately does NOT commit that reservation on
    its own — it's flushed (sent to the DB, taking the row lock) so a
    concurrent duplicate delivery still fails fast on the same primary key,
    but not committed until `_apply_webhook_event` finishes without error.

    This matters: if the reservation were committed up front and
    `_apply_webhook_event` then raised partway through (malformed event data,
    a transient DB error, ...), the event would be permanently marked
    "processed" while the actual subscription/invoice update never happened
    — and since Stripe only retries on a non-2xx response, a retry of that
    same event would hit the "already recorded" short-circuit and silently
    no-op forever, losing the update for good. Flushing-not-committing means
    a mid-processing failure rolls the reservation back together with
    whatever partial state changes were made, so a retry reprocesses the
    event from scratch instead of being told it already succeeded.
    """
    event_id = event.get("id")
    event_type = event.get("type")

    if event_id:
        already = session.get(StripeEvent, event_id)
        if already is not None:
            return
        session.add(StripeEvent(id=event_id, event_type=event_type or "unknown"))
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            return  # a concurrent request already recorded (and is applying) this event

    _apply_webhook_event(session, event)
    # If we get here, _apply_webhook_event ran to completion without raising.
    # Its own branches already call session.commit() when they do real work;
    # this is a safety-net commit for branches that intentionally no-op
    # (unknown event type, missing referenced object) so the flushed
    # reservation above still lands instead of being silently rolled back —
    # harmless either way for those cases, since redoing a no-op is a no-op.
    session.commit()


def _apply_webhook_event(session: Session, event: dict) -> None:
    """Applies the handful of Stripe events that affect billing state shown
    in-app. Unknown/irrelevant event types are ignored (Stripe sends many
    events this app doesn't need to react to)."""
    event_type = event.get("type")
    obj = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        company_id = obj.get("client_reference_id")
        if not company_id:
            return
        sub = get_or_create_subscription(session, uuid.UUID(company_id))
        is_new = sub.stripe_subscription_id is None
        sub.stripe_customer_id = obj.get("customer") or sub.stripe_customer_id
        sub.stripe_subscription_id = obj.get("subscription") or sub.stripe_subscription_id
        _billing_audit(session, sub.company_id, None,
                       "subscription.created" if is_new else "subscription.updated", None)
        session.commit()

    elif event_type in ("customer.subscription.updated", "customer.subscription.created"):
        sub = _subscription_by_stripe_id(session, obj.get("id"))
        if sub is None:
            _log_unrecognized_reference(event_type, obj.get("id"))
            return
        before_plan, before_status = sub.plan, sub.status

        items = obj.get("items", {}).get("data", [])
        price_id = items[0]["price"]["id"] if items else None
        plan = _plan_from_price_id(price_id)
        if plan is not None:
            sub.plan = plan
        try:
            sub.status = SubscriptionStatus(obj.get("status"))
        except ValueError:
            pass  # a Stripe status we don't model (e.g. "incomplete") — leave as-is
        period_end = obj.get("current_period_end")
        if period_end is not None:
            sub.current_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)
        sub.cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
        if sub.status != SubscriptionStatus.past_due:
            sub.grace_period_expires_at = None

        if plan is not None and before_plan != plan:
            action = "subscription.upgraded" if _PLAN_RANK[plan] > _PLAN_RANK[before_plan] else "subscription.downgraded"
            _billing_audit(session, sub.company_id, None, action,
                           {"from": before_plan.value, "to": plan.value})
        elif before_status != SubscriptionStatus.active and sub.status == SubscriptionStatus.active:
            _billing_audit(session, sub.company_id, None, "subscription.reactivated",
                           {"plan": sub.plan.value})
        session.commit()

    elif event_type == "customer.subscription.deleted":
        sub = _subscription_by_stripe_id(session, obj.get("id"))
        if sub is None:
            _log_unrecognized_reference(event_type, obj.get("id"))
            return
        _billing_audit(session, sub.company_id, None, "subscription.canceled", {"plan": sub.plan.value})
        sub.plan = PlanTier.free
        sub.status = SubscriptionStatus.canceled
        sub.cancel_at_period_end = False
        sub.grace_period_expires_at = None
        session.commit()

    elif event_type == "invoice.paid":
        stripe_invoice_id = obj.get("id")
        if stripe_invoice_id and session.execute(
            select(Invoice).where(Invoice.stripe_invoice_id == stripe_invoice_id)
        ).scalar_one_or_none() is not None:
            return  # already recorded

        sub = _subscription_by_stripe_id(session, obj.get("subscription"))
        if sub is None:
            _log_unrecognized_reference(event_type, obj.get("subscription"))
            return
        was_past_due = sub.status in (SubscriptionStatus.past_due, SubscriptionStatus.suspended)
        sub.status = SubscriptionStatus.active
        sub.grace_period_expires_at = None
        session.add(Invoice(
            id=uuid.uuid4(), company_id=sub.company_id, plan=sub.plan,
            amount=Decimal(obj.get("amount_paid", 0)) / 100,
            currency=(obj.get("currency") or "aud").upper(),
            period_start=datetime.fromtimestamp(obj["period_start"], tz=timezone.utc),
            period_end=datetime.fromtimestamp(obj["period_end"], tz=timezone.utc),
            stripe_invoice_id=stripe_invoice_id,
            hosted_invoice_url=obj.get("hosted_invoice_url"),
        ))
        _billing_audit(session, sub.company_id, None, "payment.succeeded",
                       {"amount": str(Decimal(obj.get("amount_paid", 0)) / 100)})
        _billing_audit(session, sub.company_id, None, "invoice.paid", {"stripe_invoice_id": stripe_invoice_id})
        if was_past_due:
            _billing_audit(session, sub.company_id, None, "subscription.reactivated",
                           {"plan": sub.plan.value, "reason": "payment_recovered"})
        session.commit()

    elif event_type == "invoice.payment_failed":
        sub = _subscription_by_stripe_id(session, obj.get("subscription"))
        if sub is None:
            _log_unrecognized_reference(event_type, obj.get("subscription"))
            return
        sub.status = SubscriptionStatus.past_due
        sub.grace_period_expires_at = _now() + timedelta(days=get_settings().billing_grace_period_days)
        _billing_audit(session, sub.company_id, None, "payment.failed",
                       {"plan": sub.plan.value, "grace_period_expires_at": sub.grace_period_expires_at.isoformat()})
        session.commit()

    elif event_type == "invoice.voided":
        stripe_invoice_id = obj.get("id")
        inv = session.execute(
            select(Invoice).where(Invoice.stripe_invoice_id == stripe_invoice_id)
        ).scalar_one_or_none() if stripe_invoice_id else None
        if inv is None:
            _log_unrecognized_reference(event_type, stripe_invoice_id)
            return
        inv.status = InvoiceStatus.void
        _billing_audit(session, inv.company_id, None, "invoice.voided", {"stripe_invoice_id": stripe_invoice_id})
        session.commit()


# -- billing audit trail ------------------------------------------------------
# Reuses the existing immutable audit_log table (entity_type="subscription")
# rather than introducing a parallel table — same append-only guarantee,
# same company-scoping, already-established convention (see
# services/orgs.py, services/invitations.py). actor_user_id is None for
# webhook-driven events (Stripe, not a person, caused the change).
def _billing_audit(session: Session, company_id: uuid.UUID, actor_user_id: uuid.UUID | None,
                   action: str, metadata: dict | None) -> None:
    session.add(AuditLog(
        company_id=company_id, actor_user_id=actor_user_id,
        entity_type="subscription", entity_id=company_id, action=action, after=metadata,
    ))


def list_billing_audit(session: Session, company_id: uuid.UUID, limit: int = 100) -> list[AuditLog]:
    return list(session.execute(
        select(AuditLog).where(AuditLog.company_id == company_id, AuditLog.entity_type == "subscription")
        .order_by(AuditLog.created_at.desc()).limit(limit)
    ).scalars().all())
