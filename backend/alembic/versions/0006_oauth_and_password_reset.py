"""OAuth identities + password reset tokens (.22 auth)

Revision ID: 0006_oauth_and_password_reset
Revises: 0005_invitation_dedup
Create Date: 2026-07-04

Adds oauth_identities (Google now; provider is a free string so
Microsoft/GitHub are new rows, not new migrations) and
password_reset_tokens (same opaque-token-hash shape as refresh_tokens),
and drops the NOT NULL constraint on users.password_hash — an OAuth-only
account genuinely has no password. Same IF-NOT-EXISTS convention as
0002-0005: 0001_initial executes the current schema.sql, so a brand new
database already has this by the time this runs.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_oauth_and_password_reset"
down_revision: Union[str, None] = "0005_invitation_dedup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;

        CREATE TABLE IF NOT EXISTS oauth_identities (
            id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider       text NOT NULL,
            provider_sub   text NOT NULL,
            email          citext NOT NULL,
            created_at     timestamptz NOT NULL DEFAULT now(),
            UNIQUE (provider, provider_sub)
        );
        CREATE INDEX IF NOT EXISTS idx_oauth_identities_user ON oauth_identities(user_id);

        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash   text NOT NULL UNIQUE,
            created_at   timestamptz NOT NULL DEFAULT now(),
            expires_at   timestamptz NOT NULL,
            used_at      timestamptz
        );
        CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user ON password_reset_tokens(user_id);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS password_reset_tokens CASCADE;
        DROP TABLE IF EXISTS oauth_identities CASCADE;
        ALTER TABLE users ALTER COLUMN password_hash SET NOT NULL;
        """
    )
