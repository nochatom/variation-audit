"""Billing provider abstraction (.23).

Mirrors the SmtpMailer/ConsoleMailer split in app/mailer.py: a real Stripe
implementation plus a Null fallback so the billing UI always renders (usage
is always real, subscription defaults to Free/active) even with no Stripe
account connected yet. Card capture always happens inside Stripe Checkout or
the Stripe Billing Portal — never on a form this app hosts, so a raw card
number is never sent to our backend either way.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class BillingNotConfigured(Exception):
    """Raised when an action needs Stripe but no secret key is configured,
    or needs a per-plan Price ID that hasn't been set yet."""


@dataclass(frozen=True)
class CheckoutSession:
    url: str


@dataclass(frozen=True)
class PortalSession:
    url: str


# Pinned explicitly (Stripe's own guidance): without this, an integration
# silently rides whatever API version is set as the account's default, which
# can change the shape of webhook payloads/objects out from under this code.
# Bump deliberately (and re-run the webhook tests) when upgrading.
_STRIPE_API_VERSION = "2024-06-20"


class BillingProvider(Protocol):
    def get_or_create_customer(self, *, company_id: str, email: str, name: str) -> str: ...

    def create_checkout_session(self, *, customer_id: str, price_id: str,
                                success_url: str, cancel_url: str,
                                client_reference_id: str, idempotency_key: str | None = None) -> CheckoutSession: ...

    def create_billing_portal_session(self, *, customer_id: str, return_url: str) -> PortalSession: ...

    def cancel_subscription(self, *, subscription_id: str) -> None: ...

    def resume_subscription(self, *, subscription_id: str) -> None: ...

    def sync_seat_overage(self, *, subscription_id: str, price_id: str, quantity: int) -> None: ...


class NullBillingProvider:
    """No Stripe secret key configured. Every action that would need a real
    payment flow raises BillingNotConfigured rather than fabricating one —
    the caller (services/billing.py) turns that into a clear 409, not a
    silent no-op or a fake checkout URL."""

    def get_or_create_customer(self, *, company_id: str, email: str, name: str) -> str:
        raise BillingNotConfigured("Stripe is not configured (VA_STRIPE_SECRET_KEY unset)")

    def create_checkout_session(self, *, customer_id: str, price_id: str,
                                success_url: str, cancel_url: str,
                                client_reference_id: str, idempotency_key: str | None = None) -> CheckoutSession:
        raise BillingNotConfigured("Stripe is not configured (VA_STRIPE_SECRET_KEY unset)")

    def create_billing_portal_session(self, *, customer_id: str, return_url: str) -> PortalSession:
        raise BillingNotConfigured("Stripe is not configured (VA_STRIPE_SECRET_KEY unset)")

    def cancel_subscription(self, *, subscription_id: str) -> None:
        raise BillingNotConfigured("Stripe is not configured (VA_STRIPE_SECRET_KEY unset)")

    def resume_subscription(self, *, subscription_id: str) -> None:
        raise BillingNotConfigured("Stripe is not configured (VA_STRIPE_SECRET_KEY unset)")

    def sync_seat_overage(self, *, subscription_id: str, price_id: str, quantity: int) -> None:
        raise BillingNotConfigured("Stripe is not configured (VA_STRIPE_SECRET_KEY unset)")


class StripeBillingProvider:
    """Real Stripe integration. Imports the `stripe` SDK lazily so a
    deployment with no Stripe account configured never needs the package
    importable at module-load time — only when this class is actually
    instantiated (see get_billing_provider() below)."""

    def __init__(self, secret_key: str):
        import stripe

        self._stripe = stripe
        self._stripe.api_key = secret_key
        self._stripe.api_version = _STRIPE_API_VERSION

    def get_or_create_customer(self, *, company_id: str, email: str, name: str) -> str:
        existing = self._stripe.Customer.list(email=email, limit=1)
        if existing.data:
            return existing.data[0].id
        # Deterministic idempotency key: at most one Stripe Customer should
        # ever be created for a given org, so this key is stable (not
        # time-windowed) — a retried/duplicate call always resolves to the
        # same Customer instead of creating a second one.
        customer = self._stripe.Customer.create(
            email=email, name=name, metadata={"company_id": company_id},
            idempotency_key=f"customer-create-{company_id}",
        )
        return customer.id

    def create_checkout_session(self, *, customer_id: str, price_id: str,
                                success_url: str, cancel_url: str,
                                client_reference_id: str, idempotency_key: str | None = None) -> CheckoutSession:
        session = self._stripe.checkout.Session.create(
            customer=customer_id,
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=client_reference_id,
            idempotency_key=idempotency_key,
        )
        return CheckoutSession(url=session.url)

    def create_billing_portal_session(self, *, customer_id: str, return_url: str) -> PortalSession:
        session = self._stripe.billing_portal.Session.create(
            customer=customer_id, return_url=return_url,
            configuration=self._ensure_portal_configuration(),
        )
        return PortalSession(url=session.url)

    def cancel_subscription(self, *, subscription_id: str) -> None:
        self._stripe.Subscription.modify(subscription_id, cancel_at_period_end=True)

    def resume_subscription(self, *, subscription_id: str) -> None:
        """Undo a pending cancel_at_period_end — the customer keeps their
        current plan instead of dropping to Free at the end of the period."""
        self._stripe.Subscription.modify(subscription_id, cancel_at_period_end=False)

    def sync_seat_overage(self, *, subscription_id: str, price_id: str, quantity: int) -> None:
        """Adds/updates/removes the seat-overage line item on an existing
        Stripe subscription so its quantity always matches the org's actual
        billable-seat overage (.25). quantity=0 removes the item entirely
        (no overage line rather than a zero-quantity one)."""
        sub = self._stripe.Subscription.retrieve(subscription_id)
        existing_item = next((i for i in sub["items"]["data"] if i["price"]["id"] == price_id), None)

        if quantity <= 0:
            if existing_item is not None:
                self._stripe.SubscriptionItem.delete(existing_item["id"])
            return

        if existing_item is not None:
            if existing_item["quantity"] != quantity:
                self._stripe.SubscriptionItem.modify(existing_item["id"], quantity=quantity)
        else:
            self._stripe.SubscriptionItem.create(
                subscription=subscription_id, price=price_id, quantity=quantity,
            )

    def _ensure_portal_configuration(self) -> str:
        """Returns the id of a Billing Portal Configuration with every
        self-serve capability enabled: update payment method (including
        replacing an expired card), invoice/payment history, billing-info
        updates, and subscription cancel. Reuses the account's existing
        active configuration if one was already created (by a previous call,
        or manually in the Stripe Dashboard) rather than creating a new one
        on every portal session."""
        existing = self._stripe.billing_portal.Configuration.list(active=True, limit=1)
        if existing.data:
            return existing.data[0].id

        configuration = self._stripe.billing_portal.Configuration.create(
            business_profile={"headline": "VariationIQ billing"},
            features={
                "customer_update": {
                    "enabled": True,
                    "allowed_updates": ["email", "name", "address", "phone", "tax_id"],
                },
                "invoice_history": {"enabled": True},
                "payment_method_update": {"enabled": True},
                "subscription_cancel": {"enabled": True},
            },
        )
        return configuration.id


def get_billing_provider() -> BillingProvider:
    """FastAPI-dependency-friendly factory (overridable in tests, mirrors
    app/mailer.py:get_mailer)."""
    from app.config import get_settings

    s = get_settings()
    if s.stripe_secret_key:
        return StripeBillingProvider(s.stripe_secret_key)
    return NullBillingProvider()
