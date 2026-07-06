"""Billing & subscriptions (.23)

Revision ID: 0007_billing
Revises: 0006_oauth_and_password_reset
Create Date: 2026-07-04

Adds subscriptions (one row per org, created lazily as Free/active on first
billing view), payment_methods (mirrored from Stripe — never a raw card
number), and invoices (mirrored from Stripe webhook events). Same
IF-NOT-EXISTS convention as 0002-0006: 0001_initial executes the current
schema.sql, so a brand new database already has this by the time this runs.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_billing"
down_revision: Union[str, None] = "0006_oauth_and_password_reset"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS subscriptions (
            id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id             uuid NOT NULL UNIQUE REFERENCES organizations(id) ON DELETE CASCADE,
            plan                   text NOT NULL DEFAULT 'free',
            status                 text NOT NULL DEFAULT 'active',
            current_period_end     timestamptz,
            cancel_at_period_end   boolean NOT NULL DEFAULT false,
            stripe_customer_id     text,
            stripe_subscription_id text,
            created_at             timestamptz NOT NULL DEFAULT now(),
            updated_at             timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_subscriptions_company ON subscriptions(company_id);

        CREATE TABLE IF NOT EXISTS payment_methods (
            id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id                uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            brand                     text NOT NULL,
            last4                     text NOT NULL,
            exp_month                 integer NOT NULL,
            exp_year                  integer NOT NULL,
            is_default                boolean NOT NULL DEFAULT true,
            stripe_payment_method_id  text UNIQUE,
            created_at                timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_payment_methods_company ON payment_methods(company_id);

        CREATE TABLE IF NOT EXISTS invoices (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id          uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            plan                text NOT NULL,
            amount              numeric(10,2) NOT NULL,
            currency            text NOT NULL DEFAULT 'AUD',
            status              text NOT NULL DEFAULT 'paid',
            period_start        timestamptz NOT NULL,
            period_end          timestamptz NOT NULL,
            stripe_invoice_id   text UNIQUE,
            hosted_invoice_url  text,
            created_at          timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_invoices_company ON invoices(company_id, created_at);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS invoices CASCADE;
        DROP TABLE IF EXISTS payment_methods CASCADE;
        DROP TABLE IF EXISTS subscriptions CASCADE;
        """
    )
