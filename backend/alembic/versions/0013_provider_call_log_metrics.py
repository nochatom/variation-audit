"""Metrics fields on provider_call_log: retries, fallback_used
(Phase 5 diagnostics — app/routers/internal_providers.py needs these for
the /metrics endpoint; they were never persisted before this migration,
only present transiently in ReliableLlm's per-call metrics dict).

Revision ID: 0013_provider_call_log_metrics
Revises: 0012_provider_health
Create Date: 2026-07-10

Additive columns only, nullable, no backfill — existing rows simply have
NULL retries/fallback_used, treated as 0/false by the aggregation queries
that read them.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013_provider_call_log_metrics"
down_revision: Union[str, None] = "0012_provider_health"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE provider_call_log ADD COLUMN IF NOT EXISTS retries integer;
        ALTER TABLE provider_call_log ADD COLUMN IF NOT EXISTS fallback_used boolean;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE provider_call_log DROP COLUMN IF EXISTS fallback_used;
        ALTER TABLE provider_call_log DROP COLUMN IF EXISTS retries;
        """
    )
