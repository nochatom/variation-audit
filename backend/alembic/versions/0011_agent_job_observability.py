"""Agent scaffold job observability: worker heartbeat, ETA, LLM metrics
(app/agents/worker.py, app/agents/reliable_llm.py).

Revision ID: 0011_agent_job_observability
Revises: 0010_agent_analysis_jobs
Create Date: 2026-07-09

Additive columns only on agent_analysis_jobs — no change to the
production analysis_jobs table or the existing SKIP-LOCKED claim pattern.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_agent_job_observability"
down_revision: Union[str, None] = "0010_agent_analysis_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE agent_analysis_jobs ADD COLUMN IF NOT EXISTS worker_id text;
        ALTER TABLE agent_analysis_jobs ADD COLUMN IF NOT EXISTS heartbeat_at timestamptz;
        ALTER TABLE agent_analysis_jobs ADD COLUMN IF NOT EXISTS last_progress_at timestamptz;
        ALTER TABLE agent_analysis_jobs ADD COLUMN IF NOT EXISTS estimated_remaining_seconds integer;
        ALTER TABLE agent_analysis_jobs ADD COLUMN IF NOT EXISTS llm_calls jsonb;

        CREATE INDEX IF NOT EXISTS idx_agent_jobs_worker ON agent_analysis_jobs (worker_id);
        CREATE INDEX IF NOT EXISTS idx_agent_jobs_heartbeat
            ON agent_analysis_jobs (status, heartbeat_at);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS idx_agent_jobs_heartbeat;
        DROP INDEX IF EXISTS idx_agent_jobs_worker;
        ALTER TABLE agent_analysis_jobs DROP COLUMN IF EXISTS llm_calls;
        ALTER TABLE agent_analysis_jobs DROP COLUMN IF EXISTS estimated_remaining_seconds;
        ALTER TABLE agent_analysis_jobs DROP COLUMN IF EXISTS last_progress_at;
        ALTER TABLE agent_analysis_jobs DROP COLUMN IF EXISTS heartbeat_at;
        ALTER TABLE agent_analysis_jobs DROP COLUMN IF EXISTS worker_id;
        """
    )
