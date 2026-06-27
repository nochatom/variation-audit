"""initial schema (baseline from backend/db/schema.sql)

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-27

Applies the canonical product schema. backend/db/schema.sql remains the single
source of truth; this baseline executes it so `alembic upgrade head` reproduces
the database exactly. Subsequent migrations should be normal Alembic revisions.
"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# backend/db/schema.sql  (versions -> alembic -> backend -> db/schema.sql)
SCHEMA_SQL = Path(__file__).resolve().parents[2] / "db" / "schema.sql"


def upgrade() -> None:
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    # Alembic manages the transaction; drop the file's own BEGIN/COMMIT wrapper.
    sql = sql.replace("BEGIN;", "").replace("COMMIT;", "")
    op.execute(sql)


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS notifications, audit_log, value_estimates, evidence,
            variations, analysis_jobs, documents, projects, memberships, users,
            organizations CASCADE;
        DROP FUNCTION IF EXISTS set_updated_at() CASCADE;
        DROP TYPE IF EXISTS basis_quality, review_status, confidence_band, variation_engine_status,
            engine_stage, job_status, source_type, project_status, membership_role;
        """
    )
