"""Append-only analysis_usage_events table — the authoritative ledger for
monthly analysis-run quota enforcement (services/billing.py).

Revision ID: 0016_analysis_usage_events
Revises: 0015_job_cancellation
Create Date: 2026-07-24

Root cause this fixes: get_usage()/enforce_analysis_limit() previously
counted rows in analysis_jobs, whose project_id FK is ON DELETE CASCADE.
Permanently deleting a project (routers/projects.py:delete_project) therefore
deleted that project's analysis_jobs rows too, silently resetting the org's
counted usage for the month — a free org could archive+delete and recreate a
project to get unlimited analyses. This table is a separate, immutable
ledger: one row is written per accepted (quota-checked) analysis run and is
never deleted by a project or job deletion (project_id/job_id are ON DELETE
SET NULL, not CASCADE), so consumed quota can only grow, never be reset by
deleting unrelated data.

Purely additive: a new table only. No changes to any existing table.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0016_analysis_usage_events"
down_revision: Union[str, None] = "0015_job_cancellation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_usage_events (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id  uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            project_id  uuid REFERENCES projects(id) ON DELETE SET NULL,
            job_id      uuid REFERENCES analysis_jobs(id) ON DELETE SET NULL,
            created_at  timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_analysis_usage_company_created
            ON analysis_usage_events (company_id, created_at);
        """
    )
    # Backfill: give existing orgs credit for analyses they've already run
    # this billing cycle, so the switchover doesn't silently grant everyone a
    # fresh 5-run allowance mid-month. Best-effort/approximate (job_id is set
    # where the job row still exists; older cascaded-away jobs can't be
    # recovered) — acceptable since this only ever adds usage, never removes
    # protection.
    op.execute(
        """
        INSERT INTO analysis_usage_events (company_id, project_id, job_id, created_at)
        SELECT company_id, project_id, id, created_at FROM analysis_jobs;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS analysis_usage_events;")
