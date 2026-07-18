"""Append-only analysis_job_events table — real worker-emitted progress
events, streamed to the client over SSE (app/routers/analysis_events.py).

Revision ID: 0014_analysis_job_events
Revises: 0013_provider_call_log_metrics
Create Date: 2026-07-14

Purely additive: a new table only. No changes to analysis_jobs or any
existing table, so existing APIs are untouched. FK to analysis_jobs with
ON DELETE CASCADE so events are cleaned up with their job.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0014_analysis_job_events"
down_revision: Union[str, None] = "0013_provider_call_log_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_job_events (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            job_id              uuid NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
            seq                 integer NOT NULL,
            stage               text NOT NULL,
            status              text NOT NULL,
            percentage          integer NOT NULL DEFAULT 0,
            current_document    text,
            processed_documents integer NOT NULL DEFAULT 0,
            total_documents     integer NOT NULL DEFAULT 0,
            variations_found    integer NOT NULL DEFAULT 0,
            evidence_links      integer NOT NULL DEFAULT 0,
            elapsed_seconds     numeric(10, 2) NOT NULL DEFAULT 0,
            estimated_remaining numeric(10, 2),
            created_at          timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_job_events_job_seq
            ON analysis_job_events (job_id, seq);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS analysis_job_events;")
