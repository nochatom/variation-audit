"""Enterprise billing: grace period, seat overrides, webhook idempotency,
document storage tracking (.24)

Revision ID: 0008_billing_enterprise
Revises: 0007_billing
Create Date: 2026-07-04

Adds subscriptions.grace_period_expires_at + included_seats, stripe_events
(webhook idempotency ledger), and documents.size_bytes (storage-limit
enforcement). Same IF-NOT-EXISTS convention as 0002-0007: 0001_initial
executes the current schema.sql, so a brand new database already has this
by the time this runs.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_billing_enterprise"
down_revision: Union[str, None] = "0007_billing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS grace_period_expires_at timestamptz;
        ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS included_seats integer;

        CREATE TABLE IF NOT EXISTS stripe_events (
            id            text PRIMARY KEY,
            event_type    text NOT NULL,
            processed_at  timestamptz NOT NULL DEFAULT now()
        );

        ALTER TABLE documents ADD COLUMN IF NOT EXISTS size_bytes integer;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE documents DROP COLUMN IF EXISTS size_bytes;
        DROP TABLE IF EXISTS stripe_events CASCADE;
        ALTER TABLE subscriptions DROP COLUMN IF EXISTS included_seats;
        ALTER TABLE subscriptions DROP COLUMN IF EXISTS grace_period_expires_at;
        """
    )
