"""invitation duplicate-prevention (.19a hardening)

Revision ID: 0005_invitation_dedup
Revises: 0004_invitations
Create Date: 2026-07-03

Adds a partial unique index enforcing at most one ACTIVE (not yet accepted
or revoked) invitation per (company_id, email) — the DB-level backstop for
services/invitations.py:create_invitation's app-level duplicate rejection,
closing the race window between two concurrent invites for the same email.

Before adding the constraint, revokes any pre-existing duplicates (keeping
the newest per company+email) so the index creation itself can't fail on a
database that predates this migration. Same IF-NOT-EXISTS convention as
0002-0004: 0001_initial executes the current schema.sql, so a brand new
database already has this index by the time this runs.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_invitation_dedup"
down_revision: Union[str, None] = "0004_invitations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        -- Revoke all but the newest active invitation per (company, email),
        -- so the unique index below has nothing to conflict with.
        WITH ranked AS (
            SELECT id, row_number() OVER (
                PARTITION BY company_id, email ORDER BY created_at DESC
            ) AS rn
            FROM invitations
            WHERE accepted_at IS NULL AND revoked_at IS NULL
        )
        UPDATE invitations SET revoked_at = now()
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1);

        CREATE UNIQUE INDEX IF NOT EXISTS idx_invitations_active_unique
            ON invitations(company_id, email)
            WHERE accepted_at IS NULL AND revoked_at IS NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_invitations_active_unique;")
