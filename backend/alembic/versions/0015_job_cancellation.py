"""Analysis-job cancellation: add the 'cancelled' status + a cancel signal.

Revision ID: 0015_job_cancellation
Revises: 0014_analysis_job_events
Create Date: 2026-07-17

Additive: a new enum value on job_status and a nullable timestamp column. No
existing rows change. `ALTER TYPE ... ADD VALUE` is allowed inside a
transaction on PostgreSQL 12+ as long as the new value isn't used in the same
transaction (it isn't here).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_job_cancellation"
down_revision: Union[str, None] = "0014_analysis_job_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'cancelled'")
    op.add_column(
        "analysis_jobs",
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    # Postgres cannot drop a single enum value; leaving 'cancelled' in place is
    # harmless. Only the column is reversible.
    op.drop_column("analysis_jobs", "cancel_requested_at")
