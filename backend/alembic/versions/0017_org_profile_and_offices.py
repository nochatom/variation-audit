"""Organisation profile columns + offices table.

Revision ID: 0017_org_profile_and_offices
Revises: 0016_analysis_usage_events
Create Date: 2026-07-25

The organizations table carried only (id, name, created_at, updated_at), and
there was no endpoint to read or write even the name — the frontend learned
the org name solely from the membership list embedded in /auth/me. Anything
that has to identify the contracting entity (a recovery report naming the
claimant, an ABN on an exported document) had nowhere to read it from.

Two additions, both purely additive:

  * organizations gains identity columns. `abn` is the Australian Business
    Number: 11 digits, stored digits-only (no spaces) so it can be compared
    and validated; the CHECK enforces shape, not the checksum, which is the
    application's job. `primary_state` is deliberately NOT a foreign key to
    anything — it's a plain AU state code used as the default jurisdiction
    for new projects, and security-of-payment regimes are state-based, so
    getting it wrong has time-bar consequences.

  * offices is a new table. One org has many offices; exactly one may be
    primary, enforced by a partial unique index rather than application code,
    because "two primary offices" is the kind of invariant that survives any
    amount of careful service-layer discipline right up until a concurrent
    write.

logo_key follows the storage convention used by project documents: the
object-storage key only, never a URL — signed URLs are minted at read time.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0017_org_profile_and_offices"
down_revision: Union[str, None] = "0016_analysis_usage_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AU_STATES = "('NSW','VIC','QLD','WA','SA','TAS','ACT','NT')"


def upgrade() -> None:
    op.execute(
        f"""
        ALTER TABLE organizations
            ADD COLUMN IF NOT EXISTS legal_name    text,
            ADD COLUMN IF NOT EXISTS abn           text,
            ADD COLUMN IF NOT EXISTS acn           text,
            ADD COLUMN IF NOT EXISTS website       text,
            ADD COLUMN IF NOT EXISTS phone         text,
            ADD COLUMN IF NOT EXISTS logo_key      text,
            ADD COLUMN IF NOT EXISTS primary_state text;

        ALTER TABLE organizations
            DROP CONSTRAINT IF EXISTS ck_organizations_abn;
        ALTER TABLE organizations
            ADD CONSTRAINT ck_organizations_abn
            CHECK (abn IS NULL OR abn ~ '^[0-9]{{11}}$');

        ALTER TABLE organizations
            DROP CONSTRAINT IF EXISTS ck_organizations_acn;
        ALTER TABLE organizations
            ADD CONSTRAINT ck_organizations_acn
            CHECK (acn IS NULL OR acn ~ '^[0-9]{{9}}$');

        ALTER TABLE organizations
            DROP CONSTRAINT IF EXISTS ck_organizations_primary_state;
        ALTER TABLE organizations
            ADD CONSTRAINT ck_organizations_primary_state
            CHECK (primary_state IS NULL OR primary_state IN {_AU_STATES});

        CREATE TABLE IF NOT EXISTS offices (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id  uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            label       text NOT NULL,
            address     text,
            suburb      text,
            state       text,
            postcode    text,
            phone       text,
            is_primary  boolean NOT NULL DEFAULT false,
            created_at  timestamptz NOT NULL DEFAULT now(),
            updated_at  timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_offices_state
                CHECK (state IS NULL OR state IN {_AU_STATES}),
            CONSTRAINT ck_offices_postcode
                CHECK (postcode IS NULL OR postcode ~ '^[0-9]{{4}}$')
        );

        CREATE INDEX IF NOT EXISTS idx_offices_company
            ON offices (company_id);

        -- At most one primary office per org, enforced by the database.
        CREATE UNIQUE INDEX IF NOT EXISTS uq_offices_one_primary
            ON offices (company_id) WHERE is_primary;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS offices;
        ALTER TABLE organizations
            DROP CONSTRAINT IF EXISTS ck_organizations_abn,
            DROP CONSTRAINT IF EXISTS ck_organizations_acn,
            DROP CONSTRAINT IF EXISTS ck_organizations_primary_state;
        ALTER TABLE organizations
            DROP COLUMN IF EXISTS legal_name,
            DROP COLUMN IF EXISTS abn,
            DROP COLUMN IF EXISTS acn,
            DROP COLUMN IF EXISTS website,
            DROP COLUMN IF EXISTS phone,
            DROP COLUMN IF EXISTS logo_key,
            DROP COLUMN IF EXISTS primary_state;
        """
    )
