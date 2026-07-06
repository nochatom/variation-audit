"""Remove Google OAuth identities (switching to Supabase Authentication)

Revision ID: 0009_remove_google_oauth
Revises: 0008_billing_enterprise
Create Date: 2026-07-05

Drops oauth_identities — it only ever held Google-linked accounts, and
Google Identity Services has been removed from the app in favour of a
planned Supabase Authentication integration (which will manage identity
linking on its own terms, not via this table). users.password_hash stays
nullable: an SSO-only account (Supabase-authenticated, once that lands)
still genuinely has no local password, same reasoning as when this was
introduced for Google in 0006.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_remove_google_oauth"
down_revision: Union[str, None] = "0008_billing_enterprise"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS oauth_identities CASCADE;")


def downgrade() -> None:
    op.execute(
        """
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
        """
    )
