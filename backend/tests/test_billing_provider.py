"""StripeBillingProvider (.23/.24): pinned API version, idempotency keys,
portal configuration reuse — the actual Stripe call construction, as opposed
to services/billing.py's business logic (covered in test_billing.py against
a fake provider)."""
import uuid
from types import SimpleNamespace

from app.billing.provider import StripeBillingProvider, _STRIPE_API_VERSION


class _FakeStripeObject(SimpleNamespace):
    """Mimics a Stripe SDK response object (attribute access, e.g. `.id`)."""


class _FakeCollection(SimpleNamespace):
    """Mimics a Stripe SDK list response (`.data`)."""


class _RecordingCustomer:
    def __init__(self, calls, existing=None):
        self._calls = calls
        self._existing = existing or []

    def list(self, **kwargs):
        self._calls.append(("Customer.list", kwargs))
        return _FakeCollection(data=self._existing)

    def create(self, **kwargs):
        self._calls.append(("Customer.create", kwargs))
        return _FakeStripeObject(id="cus_new123")


class _RecordingCheckoutSession:
    def __init__(self, calls):
        self._calls = calls

    def create(self, **kwargs):
        self._calls.append(("checkout.Session.create", kwargs))
        return _FakeStripeObject(url="https://checkout.stripe.com/real-session")


class _RecordingPortalConfiguration:
    def __init__(self, calls, existing=None):
        self._calls = calls
        self._existing = existing or []

    def list(self, **kwargs):
        self._calls.append(("Configuration.list", kwargs))
        return _FakeCollection(data=self._existing)

    def create(self, **kwargs):
        self._calls.append(("Configuration.create", kwargs))
        return _FakeStripeObject(id="bpc_new123")


class _RecordingPortalSession:
    def __init__(self, calls):
        self._calls = calls

    def create(self, **kwargs):
        self._calls.append(("billing_portal.Session.create", kwargs))
        return _FakeStripeObject(url="https://billing.stripe.com/real-portal")


def _make_provider(calls, *, existing_customers=None, existing_configs=None):
    provider = StripeBillingProvider("sk_test_fake")
    fake_stripe = SimpleNamespace(
        api_key=None,
        api_version=None,
        Customer=_RecordingCustomer(calls, existing=existing_customers),
        checkout=SimpleNamespace(Session=_RecordingCheckoutSession(calls)),
        billing_portal=SimpleNamespace(
            Configuration=_RecordingPortalConfiguration(calls, existing=existing_configs),
            Session=_RecordingPortalSession(calls),
        ),
        Subscription=SimpleNamespace(
            modify=lambda sub_id, **kw: calls.append(("Subscription.modify", {"id": sub_id, **kw})),
        ),
    )
    provider._stripe = fake_stripe
    return provider, fake_stripe


def test_api_version_is_pinned_on_the_real_stripe_module():
    calls = []
    _, fake_stripe = _make_provider(calls)
    # __init__ already ran against the real `stripe` module before we swapped
    # `_stripe` out for the fake above — construct a second instance to
    # observe what __init__ itself sets on whatever module it's given.
    provider2 = StripeBillingProvider("sk_test_fake")
    assert provider2._stripe.api_version == _STRIPE_API_VERSION


def test_get_or_create_customer_new_customer_uses_deterministic_idempotency_key():
    calls = []
    provider, _ = _make_provider(calls)
    company_id = str(uuid.uuid4())
    customer_id = provider.get_or_create_customer(company_id=company_id, email="a@b.com", name="Acme")
    assert customer_id == "cus_new123"
    create_call = next(c for c in calls if c[0] == "Customer.create")
    assert create_call[1]["idempotency_key"] == f"customer-create-{company_id}"


def test_get_or_create_customer_existing_customer_skips_create():
    calls = []
    existing = [_FakeStripeObject(id="cus_existing456")]
    provider, _ = _make_provider(calls, existing_customers=existing)
    customer_id = provider.get_or_create_customer(company_id=str(uuid.uuid4()), email="a@b.com", name="Acme")
    assert customer_id == "cus_existing456"
    assert not any(c[0] == "Customer.create" for c in calls)


def test_create_checkout_session_forwards_idempotency_key():
    calls = []
    provider, _ = _make_provider(calls)
    result = provider.create_checkout_session(
        customer_id="cus_1", price_id="price_1",
        success_url="https://app/success", cancel_url="https://app/cancel",
        client_reference_id="cid_1", idempotency_key="checkout-cid_1-pro-12345",
    )
    assert result.url == "https://checkout.stripe.com/real-session"
    create_call = next(c for c in calls if c[0] == "checkout.Session.create")
    assert create_call[1]["idempotency_key"] == "checkout-cid_1-pro-12345"
    assert create_call[1]["mode"] == "subscription"


def test_portal_configuration_reused_when_one_already_exists():
    calls = []
    existing_config = [_FakeStripeObject(id="bpc_existing")]
    provider, _ = _make_provider(calls, existing_configs=existing_config)
    result = provider.create_billing_portal_session(customer_id="cus_1", return_url="https://app/billing")
    assert result.url == "https://billing.stripe.com/real-portal"
    assert not any(c[0] == "Configuration.create" for c in calls)
    session_call = next(c for c in calls if c[0] == "billing_portal.Session.create")
    assert session_call[1]["configuration"] == "bpc_existing"


def test_portal_configuration_created_when_none_exists():
    calls = []
    provider, _ = _make_provider(calls, existing_configs=[])
    provider.create_billing_portal_session(customer_id="cus_1", return_url="https://app/billing")
    config_call = next(c for c in calls if c[0] == "Configuration.create")
    assert config_call[1]["features"]["payment_method_update"]["enabled"] is True
    assert config_call[1]["features"]["invoice_history"]["enabled"] is True
    assert config_call[1]["features"]["subscription_cancel"]["enabled"] is True


def test_cancel_and_resume_toggle_cancel_at_period_end():
    calls = []
    provider, _ = _make_provider(calls)
    provider.cancel_subscription(subscription_id="sub_1")
    provider.resume_subscription(subscription_id="sub_1")
    assert ("Subscription.modify", {"id": "sub_1", "cancel_at_period_end": True}) in calls
    assert ("Subscription.modify", {"id": "sub_1", "cancel_at_period_end": False}) in calls
