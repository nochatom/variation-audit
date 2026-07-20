"""Billing & subscription endpoints (.23) — admin-only, org-scoped.

Every endpoint under /orgs/{company_id}/billing requires the caller to be an
admin of that exact organization (require_admin — same RBAC guard used by
orgs.py/team management), so members never see billing at all and cross-tenant
access is impossible (company_id is validated against the caller's own
membership on every request, not trusted from the URL alone).

The Stripe webhook is a separate, unauthenticated-by-JWT router: Stripe's
servers call it directly, so it's verified instead by HMAC signature
(stripe.Webhook.construct_event) against VA_STRIPE_WEBHOOK_SECRET.
"""
from __future__ import annotations

import uuid

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, get_db, require_admin
from app.billing.provider import BillingNotConfigured
from app.config import get_settings
from app.logging_config import security_logger
from app.models import AuditLog, Invoice, PlanTier, Subscription, User
from app.posthog_client import posthog_client
from app.rate_limit import BILLING_LIMIT, limiter
from app.services import billing as billing_service

router = APIRouter(prefix="/orgs/{company_id}/billing", tags=["billing"])
webhook_router = APIRouter(tags=["billing"])


# ---- schemas ---------------------------------------------------------------
class SubscriptionOut(BaseModel):
    plan: str
    status: str
    current_period_end: str | None
    cancel_at_period_end: bool
    has_payment_method: bool
    # Additive (.24) — NULL unless status is past_due. Lets the dashboard
    # show "your payment failed, update your card by <date>" without a
    # separate endpoint.
    grace_period_expires_at: str | None = None


class UsageOut(BaseModel):
    plan: str
    period_start: str
    projects_active: int
    projects_limit: int | None
    documents_processed: int
    documents_limit: int | None
    analysis_runs: int
    analysis_runs_limit: int | None
    seats_limit: int | None


class SeatsOut(BaseModel):
    current_seats: int
    included_seats: int | None
    billable_seats: int
    additional_seats: int


class FeaturesOut(BaseModel):
    audit_log: bool
    exports: bool
    sso: bool
    priority_support: bool
    advanced_analytics: bool


class CheckoutRequest(BaseModel):
    plan: PlanTier
    # Annual pricing (.25) — additive; existing callers that omit this field
    # keep getting monthly checkout, unchanged.
    billing_interval: Literal["monthly", "annual"] = "monthly"


class UrlOut(BaseModel):
    url: str


class InvoiceOut(BaseModel):
    id: str
    plan: str
    amount: str
    currency: str
    status: str
    period_start: str
    period_end: str
    hosted_invoice_url: str | None


class BillingAuditEntryOut(BaseModel):
    id: str
    actor_user_id: str | None
    action: str
    metadata: dict | None
    created_at: str


def _sub_out(sub: Subscription) -> SubscriptionOut:
    return SubscriptionOut(
        plan=sub.plan.value, status=sub.status.value,
        current_period_end=sub.current_period_end.isoformat() if sub.current_period_end else None,
        cancel_at_period_end=sub.cancel_at_period_end,
        has_payment_method=sub.stripe_customer_id is not None,
        grace_period_expires_at=sub.grace_period_expires_at.isoformat()
        if sub.grace_period_expires_at else None,
    )


def _invoice_out(inv: Invoice) -> InvoiceOut:
    return InvoiceOut(
        id=str(inv.id), plan=inv.plan.value, amount=str(inv.amount), currency=inv.currency,
        status=inv.status.value, period_start=inv.period_start.isoformat(),
        period_end=inv.period_end.isoformat(), hosted_invoice_url=inv.hosted_invoice_url,
    )


def _audit_out(a: AuditLog) -> BillingAuditEntryOut:
    return BillingAuditEntryOut(
        id=str(a.id), actor_user_id=str(a.actor_user_id) if a.actor_user_id else None,
        action=a.action, metadata=a.after, created_at=a.created_at.isoformat() if a.created_at else "",
    )


# ---- endpoints ---------------------------------------------------------------
@router.get("/subscription", response_model=SubscriptionOut)
def get_subscription(company_id: uuid.UUID, user: User = Depends(get_current_user),
                     session: Session = Depends(get_db)) -> SubscriptionOut:
    require_admin(session, user, company_id)
    sub = billing_service.get_or_create_subscription(session, company_id)
    return _sub_out(sub)


@router.get("/usage", response_model=UsageOut)
def get_usage(company_id: uuid.UUID, user: User = Depends(get_current_user),
             session: Session = Depends(get_db)) -> UsageOut:
    require_admin(session, user, company_id)
    return UsageOut(**billing_service.get_usage(session, company_id))


@router.post("/checkout", response_model=UrlOut)
@limiter.limit(BILLING_LIMIT)
def create_checkout(request: Request, response: Response, company_id: uuid.UUID, req: CheckoutRequest,
                    user: User = Depends(get_current_user),
                    session: Session = Depends(get_db)) -> UrlOut:
    require_admin(session, user, company_id)
    try:
        result = billing_service.start_checkout(session, company_id, user, req.plan, req.billing_interval)
    except billing_service.PlanNotConfigured:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "this plan isn't available for self-serve checkout yet — contact sales")
    except billing_service.AlreadyOnPaidPlan as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except BillingNotConfigured as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    posthog_client.capture(
        "checkout_initiated",
        distinct_id=str(user.id),
        properties={
            "plan": req.plan.value,
            "billing_interval": req.billing_interval,
        },
    )
    return UrlOut(url=result.url)


@router.post("/portal", response_model=UrlOut)
@limiter.limit(BILLING_LIMIT)
def create_portal(request: Request, response: Response, company_id: uuid.UUID,
                  user: User = Depends(get_current_user),
                  session: Session = Depends(get_db)) -> UrlOut:
    require_admin(session, user, company_id)
    try:
        result = billing_service.start_billing_portal(session, company_id, user)
    except BillingNotConfigured as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return UrlOut(url=result.url)


@router.post("/cancel", response_model=SubscriptionOut)
@limiter.limit(BILLING_LIMIT)
def cancel(request: Request, response: Response, company_id: uuid.UUID,
          user: User = Depends(get_current_user),
          session: Session = Depends(get_db)) -> SubscriptionOut:
    require_admin(session, user, company_id)
    try:
        sub = billing_service.cancel_subscription(session, company_id, user)
    except billing_service.NoActiveSubscription as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    posthog_client.capture(
        "subscription_cancelled",
        distinct_id=str(user.id),
        properties={"plan": sub.plan.value},
    )
    return _sub_out(sub)


@router.post("/resume", response_model=SubscriptionOut)
@limiter.limit(BILLING_LIMIT)
def resume(request: Request, response: Response, company_id: uuid.UUID,
          user: User = Depends(get_current_user),
          session: Session = Depends(get_db)) -> SubscriptionOut:
    """Undo a pending cancellation — the org keeps its current plan instead
    of dropping to Free at the end of the billing period."""
    require_admin(session, user, company_id)
    try:
        sub = billing_service.resume_subscription(session, company_id, user)
    except billing_service.NoActiveSubscription as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return _sub_out(sub)


@router.get("/invoices", response_model=list[InvoiceOut])
def list_invoices(company_id: uuid.UUID, user: User = Depends(get_current_user),
                  session: Session = Depends(get_db)) -> list[InvoiceOut]:
    require_admin(session, user, company_id)
    return [_invoice_out(i) for i in billing_service.list_invoices(session, company_id)]


@router.get("/seats", response_model=SeatsOut)
def get_seats(company_id: uuid.UUID, user: User = Depends(get_current_user),
             session: Session = Depends(get_db)) -> SeatsOut:
    """Seat-based billing groundwork (.24) — current/included/billable seats,
    exposed even though no per-seat Stripe price is wired up yet."""
    require_admin(session, user, company_id)
    return SeatsOut(**billing_service.get_seats(session, company_id))


@router.get("/features", response_model=FeaturesOut)
def get_features(company_id: uuid.UUID, user: User = Depends(get_current_user),
                 session: Session = Depends(get_db)) -> FeaturesOut:
    """Plan capability flags (.24) — the frontend consumes this instead of
    hardcoding its own plan → feature logic."""
    require_admin(session, user, company_id)
    return FeaturesOut(**billing_service.get_features(session, company_id))


@router.get("/audit", response_model=list[BillingAuditEntryOut])
def get_billing_audit(company_id: uuid.UUID, user: User = Depends(get_current_user),
                      session: Session = Depends(get_db)) -> list[BillingAuditEntryOut]:
    """Immutable billing audit trail (.24) — subscription lifecycle, payment
    outcomes, and billing portal access for this organization."""
    require_admin(session, user, company_id)
    return [_audit_out(a) for a in billing_service.list_billing_audit(session, company_id)]


# ---- Stripe webhook (public, signature-verified — not JWT/RBAC-gated) -----
# Exempt from the app-wide per-IP rate limit: Stripe's webhook calls come
# from Stripe's own infrastructure (not per-customer IPs), authenticity is
# already enforced by signature verification below, and throttling this
# endpoint would just cause Stripe to burn retry attempts for no benefit —
# same reasoning as the /health exemption in app/main.py.
@webhook_router.post("/billing/webhook", status_code=status.HTTP_204_NO_CONTENT)
@limiter.exempt
async def stripe_webhook(request: Request, session: Session = Depends(get_db)) -> None:
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "webhooks not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    import stripe

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        security_logger.warning("stripe webhook rejected: bad signature",
                                extra={"event": "stripe_webhook_invalid_signature"})
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid signature")

    billing_service.handle_webhook_event(session, event)
    security_logger.info("stripe webhook processed",
                         extra={"event": "stripe_webhook_processed", "stripe_event_type": event.get("type")})
