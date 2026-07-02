"""project soft-archive (archived_at)

Revision ID: 0003_project_archive
Revises: 0002_refresh_tokens
Create Date: 2026-07-02

Adds projects.archived_at (timestamptz, NULL = active). Same IF-NOT-EXISTS
convention as 0002: 0001_initial executes the current schema.sql, so a brand
new database already has the column by the time this runs; a database that
migrated earlier gets it here. Safe either way.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_project_archive"
down_revision: Union[str, None] = "0002_refresh_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS archived_at timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS archived_at")
