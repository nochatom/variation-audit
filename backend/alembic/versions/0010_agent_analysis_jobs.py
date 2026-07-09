"""Agent scaffold job queue (app/agents/) — additive, separate from
analysis_jobs (the production worker->engine pipeline's own table).

Revision ID: 0010_agent_analysis_jobs
Revises: 0009_remove_google_oauth
Create Date: 2026-07-09

Same DB-backed SKIP-LOCKED queue pattern as analysis_jobs; a distinct table
so the ADK multi-agent scaffold's lifecycle (pending/queued/processing/
completed/failed, current_agent, progress_percent) never touches the
engine-contract-shaped analysis_jobs schema.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_agent_analysis_jobs"
down_revision: Union[str, None] = "0009_remove_google_oauth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE agent_job_status AS ENUM
                ('pending', 'queued', 'processing', 'completed', 'failed');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;

        CREATE TABLE IF NOT EXISTS agent_analysis_jobs (
            id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id        uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            project_id        uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            created_by        uuid REFERENCES users(id) ON DELETE SET NULL,
            status            agent_job_status NOT NULL DEFAULT 'pending',
            current_agent     text,
            progress_percent  integer NOT NULL DEFAULT 0
                                CHECK (progress_percent BETWEEN 0 AND 100),
            result            jsonb,
            error_code        text,
            error_message     text,
            created_at        timestamptz NOT NULL DEFAULT now(),
            updated_at        timestamptz NOT NULL DEFAULT now(),
            started_at        timestamptz,
            completed_at      timestamptz
        );

        CREATE INDEX IF NOT EXISTS idx_agent_jobs_queue
            ON agent_analysis_jobs (status, created_at);
        CREATE INDEX IF NOT EXISTS idx_agent_jobs_project
            ON agent_analysis_jobs (project_id);
        CREATE INDEX IF NOT EXISTS idx_agent_jobs_company
            ON agent_analysis_jobs (company_id);

        DO $$ BEGIN
            CREATE TRIGGER trg_agent_analysis_jobs_updated_at
                BEFORE UPDATE ON agent_analysis_jobs
                FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_agent_analysis_jobs_updated_at ON agent_analysis_jobs;
        DROP TABLE IF EXISTS agent_analysis_jobs CASCADE;
        DROP TYPE IF EXISTS agent_job_status;
        """
    )
