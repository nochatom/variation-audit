"""refresh tokens (.2.1 JWT refresh + revocation)

Revision ID: 0002_refresh_tokens
Revises: 0001_initial
Create Date: 2026-07-01

Adds the refresh_tokens table (see backend/db/schema.sql). Uses IF NOT EXISTS:
0001_initial re-executes the *current* backend/db/schema.sql at run time (not
a frozen snapshot), so on a brand-new database it will have already created
this table by the time 0002 runs; on a database that migrated through 0001
before this table existed, 0002 is what actually adds it. Either way this
migration is a safe no-op-or-create.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_refresh_tokens"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id          uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash       text NOT NULL UNIQUE,
            created_at       timestamptz NOT NULL DEFAULT now(),
            expires_at       timestamptz NOT NULL,
            revoked_at       timestamptz,
            replaced_by_id   uuid REFERENCES refresh_tokens(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS refresh_tokens CASCADE;")
