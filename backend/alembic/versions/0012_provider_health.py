"""Provider Router health/circuit persistence (app/agents/provider_health.py,
app/agents/circuit_breaker.py) — Phase 3 of the additive Provider Router
build (docs/decisions/26-provider-router-implementation-plan.md).

Revision ID: 0012_provider_health
Revises: 0011_agent_job_observability
Create Date: 2026-07-10

Two new, empty tables. No existing table (including agent_analysis_jobs)
is touched. Nothing reads or writes these tables yet — ProviderRouter,
model_provider.py, and worker.py are all unmodified in this phase; wiring
a real DB-backed CircuitSource/HealthSource into production selection is a
later, separate step.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012_provider_health"
down_revision: Union[str, None] = "0011_agent_job_observability"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_call_log (
            id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            provider          text NOT NULL,
            model             text NOT NULL,
            selection_id      uuid,
            success           boolean NOT NULL,
            error_code        text,
            latency_ms        integer,
            input_tokens      integer,
            output_tokens     integer,
            created_at        timestamptz NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_provider_call_log_provider_time
            ON provider_call_log (provider, created_at);

        CREATE TABLE IF NOT EXISTS provider_circuit_state (
            provider          text PRIMARY KEY,
            state             text NOT NULL DEFAULT 'closed',
            failure_count     integer NOT NULL DEFAULT 0,
            opened_at         timestamptz,
            last_success      timestamptz,
            last_failure      timestamptz
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS provider_circuit_state CASCADE;
        DROP TABLE IF EXISTS provider_call_log CASCADE;
        """
    )
