"""organization invitations (.19a)

Revision ID: 0004_invitations
Revises: 0003_project_archive
Create Date: 2026-07-03

Adds the invitations table (see backend/db/schema.sql). Same IF-NOT-EXISTS
convention as 0002/0003: 0001_initial executes the current schema.sql, so a
brand new database already has this table by the time this runs; a database
that migrated earlier gets it here. Safe either way.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_invitations"
down_revision: Union[str, None] = "0003_project_archive"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS invitations (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id   uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            email        citext NOT NULL,
            role         membership_role NOT NULL DEFAULT 'member',
            token_hash   text NOT NULL UNIQUE,
            invited_by   uuid REFERENCES users(id) ON DELETE SET NULL,
            created_at   timestamptz NOT NULL DEFAULT now(),
            expires_at   timestamptz NOT NULL,
            accepted_at  timestamptz,
            accepted_by  uuid REFERENCES users(id) ON DELETE SET NULL,
            revoked_at   timestamptz
        );
        CREATE INDEX IF NOT EXISTS idx_invitations_company ON invitations(company_id);
        CREATE INDEX IF NOT EXISTS idx_invitations_email ON invitations(email);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS invitations CASCADE;")
