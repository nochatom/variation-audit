-- Variation Audit — Product Database Schema (PostgreSQL)
-- Scope: Australia only, all construction trades. Engine is STATELESS; this product DB owns ALL persistence.
-- Aligns with: docs/architecture.md §5 and docs/engine-product-api-contract-v1.1.md.
-- Conventions: UUID PKs, timestamptz, every tenant table carries company_id for org-scoped isolation.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS citext;     -- case-insensitive email

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------
CREATE TYPE membership_role        AS ENUM ('admin', 'member');
CREATE TYPE project_status         AS ENUM ('in_progress', 'completed');
CREATE TYPE source_type            AS ENUM ('email', 'rfi', 'site_instruction', 'meeting_note', 'sms', 'document');
CREATE TYPE job_status             AS ENUM ('queued', 'running', 'succeeded', 'failed');
CREATE TYPE engine_stage           AS ENUM ('ingest', 'baseline', 'classify', 'quantify', 'confidence');
CREATE TYPE variation_engine_status AS ENUM ('detected', 'confirmed', 'uncertain');
CREATE TYPE confidence_band        AS ENUM ('low', 'medium', 'high');
CREATE TYPE review_status          AS ENUM ('pending', 'confirmed', 'rejected');
CREATE TYPE basis_quality          AS ENUM ('boq', 'rate_card', 'inferred', 'none');

-- ---------------------------------------------------------------------------
-- updated_at trigger
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- Tenancy: organizations, users, memberships
-- ---------------------------------------------------------------------------
CREATE TABLE organizations (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_org_updated BEFORE UPDATE ON organizations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE users (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email          citext NOT NULL UNIQUE,
    full_name      text,
    password_hash  text NOT NULL,
    is_active      boolean NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE memberships (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company_id  uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    role        membership_role NOT NULL DEFAULT 'member',
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, company_id)
);
CREATE INDEX idx_memberships_company ON memberships(company_id);

-- ---------------------------------------------------------------------------
-- Projects & documents
-- ---------------------------------------------------------------------------
CREATE TABLE projects (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name          text NOT NULL,
    project_type  text NOT NULL DEFAULT 'construction_trade',
    country       char(2) NOT NULL DEFAULT 'AU' CHECK (country = 'AU'),  -- MVP: AU only
    status        project_status NOT NULL DEFAULT 'in_progress',
    contract_text text,                                          -- engine baseline input (contract v1.2)
    scope_text    text,                                          -- scope / BOQ
    state         varchar(8),                                    -- AU state/territory (SoP regime hint)
    created_by    uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_projects_company ON projects(company_id);
CREATE TRIGGER trg_projects_updated BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE documents (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),  -- = contract document_id
    company_id    uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id    uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_type   source_type NOT NULL,
    doc_timestamp timestamptz,                                  -- contract documents[].timestamp
    source        text,                                         -- email thread / file / system
    storage_key   text NOT NULL,                                -- S3 ap-southeast-2 object key
    content_hash  text,                                         -- dedup / integrity
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_documents_project ON documents(project_id);
CREATE INDEX idx_documents_company ON documents(company_id);

-- ---------------------------------------------------------------------------
-- Analysis jobs (mirror of engine job; request_id = idempotency key)
-- ---------------------------------------------------------------------------
CREATE TABLE analysis_jobs (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),  -- product job_id
    company_id       uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id       uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    request_id       uuid NOT NULL UNIQUE,                        -- contract §3.1 idempotency
    contract_version text NOT NULL DEFAULT 'v1.2',
    created_by       uuid REFERENCES users(id) ON DELETE SET NULL,  -- who triggered (for notifications)
    baseline         jsonb,                                       -- engine baseline rollup (notice/time_bar/sop/counts)
    recoverable_total numeric(14,2),
    time_bar_at_risk integer,
    engine_job_id    text,                                        -- id returned by engine POST
    engine_version   text,                                        -- from engine result
    status           job_status NOT NULL DEFAULT 'queued',
    progress_stage   engine_stage,
    progress_percent numeric(4,3) CHECK (progress_percent BETWEEN 0 AND 1),
    result_ref       text,                                        -- set when result >1MB (result_url)
    error_code       text,
    error_message    text,
    error_retryable  boolean,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    started_at       timestamptz,                                 -- worker began running
    finished_at      timestamptz                                  -- terminal state reached
);
CREATE INDEX idx_jobs_project ON analysis_jobs(project_id);
CREATE INDEX idx_jobs_company ON analysis_jobs(company_id);
-- Queue claim pattern: SELECT ... WHERE status='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED
CREATE INDEX idx_jobs_queue ON analysis_jobs(status, created_at);
CREATE TRIGGER trg_jobs_updated BEFORE UPDATE ON analysis_jobs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- Variations (engine output copied in for the review workflow)
-- ---------------------------------------------------------------------------
CREATE TABLE variations (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),  -- = contract variation_id
    company_id       uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id       uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    job_id           uuid NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
    title            text NOT NULL,
    description      text,
    engine_status    variation_engine_status NOT NULL DEFAULT 'detected',
    confidence_score numeric(4,3) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    confidence_band  confidence_band NOT NULL,                    -- engine-derived (low<0.5<=med<0.8<=high)
    confidence_factors jsonb,                                     -- engine deterministic breakdown
    time_bar_risk    boolean NOT NULL DEFAULT false,              -- AU SoP entitlement may be time-barred
    review_status    review_status NOT NULL DEFAULT 'pending',    -- human confirm/reject
    reviewed_by      uuid REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at      timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_variations_job ON variations(job_id);
CREATE INDEX idx_variations_project ON variations(project_id);
CREATE INDEX idx_variations_company ON variations(company_id);
CREATE INDEX idx_variations_review ON variations(review_status);

CREATE TABLE evidence (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    variation_id       uuid NOT NULL REFERENCES variations(id) ON DELETE CASCADE,
    source_type        source_type NOT NULL,
    source_document_id uuid REFERENCES documents(id) ON DELETE SET NULL,  -- traceability
    reference          text,                                     -- human-readable locator
    quote              text,                                     -- excerpt
    created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_evidence_variation ON evidence(variation_id);
CREATE INDEX idx_evidence_document ON evidence(source_document_id);

CREATE TABLE value_estimates (
    id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    variation_id              uuid NOT NULL UNIQUE REFERENCES variations(id) ON DELETE CASCADE,
    amount                    numeric(14,2),
    estimate_low              numeric(14,2),
    estimate_high             numeric(14,2),
    currency                  char(3) NOT NULL DEFAULT 'AUD' CHECK (currency = 'AUD'),
    basis_quality             basis_quality NOT NULL DEFAULT 'none',
    valuation_confidence_score numeric(4,3) CHECK (valuation_confidence_score BETWEEN 0 AND 1),
    confidence                confidence_band NOT NULL,          -- low/medium/high (same band map)
    created_at                timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Audit log (immutable) & notifications
-- ---------------------------------------------------------------------------
CREATE TABLE audit_log (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    entity_type   text NOT NULL,                                 -- 'variation' | 'project' | 'job' | ...
    entity_id     uuid NOT NULL,
    action        text NOT NULL,                                 -- 'confirm' | 'reject' | 'create' | ...
    before        jsonb,
    after         jsonb,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_company ON audit_log(company_id);
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
-- Immutability is enforced by app policy + restricted grants (no UPDATE/DELETE for app role).

CREATE TABLE review_comments (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    variation_id   uuid NOT NULL REFERENCES variations(id) ON DELETE CASCADE,
    author_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    body           text NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_review_comments_variation ON review_comments(variation_id, created_at);

CREATE TABLE notifications (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type        text NOT NULL,                                   -- 'analysis_complete' | 'analysis_failed' | ...
    payload     jsonb NOT NULL DEFAULT '{}'::jsonb,
    read_at     timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_notifications_user ON notifications(user_id, read_at);

COMMIT;
