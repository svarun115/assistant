-- =============================================================================
-- assistant_system database — shared infrastructure state
--
-- Run once on the Azure PostgreSQL server (as journaladmin or superuser):
--
--   psql "host=... dbname=postgres user=journaladmin ..." \
--       -f create_assistant_system.sql
--
-- Tables:
--   threads            — conversation thread metadata (replaces journal_threads_meta.db)
--   scheduler          — background/foreground agent schedules
--   notifications      — agent → COS delivery queue
--   artifacts          — agent outputs (daily_plan, email_digest, retro, etc.)
--   cos_trust_registry — cross-COS federation trust (Phase 2+)
--
-- Every table has user_id for multi-user isolation.
-- RLS enforced at DB level via app.user_id session variable.
-- =============================================================================

-- Create the database (run as superuser / postgres user)
CREATE DATABASE assistant_system;

-- Connect to it before running the rest:
-- \c assistant_system

-- =============================================================================
-- Row-Level Security helper
-- Gateway sets this at connection time: SET app.user_id = 'varun';
-- =============================================================================

-- threads — conversation thread metadata
-- (LangGraph checkpoint state lives in langgraph_checkpoints, managed by
--  langgraph-checkpoint-postgres; this table adds listing/search/metadata)
CREATE TABLE threads (
    thread_id       TEXT        NOT NULL,
    user_id         TEXT        NOT NULL,
    title           TEXT        NOT NULL DEFAULT 'New Conversation',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    message_count   INT         NOT NULL DEFAULT 0,
    total_input_tokens  BIGINT  NOT NULL DEFAULT 0,
    total_output_tokens BIGINT  NOT NULL DEFAULT 0,
    mode            TEXT        NOT NULL DEFAULT 'chat',
    target_date     DATE,
    model_provider  TEXT,
    model_name      TEXT,
    is_deleted      BOOLEAN     NOT NULL DEFAULT FALSE,
    emoji           TEXT,
    PRIMARY KEY (thread_id, user_id)
);

ALTER TABLE threads ENABLE ROW LEVEL SECURITY;
CREATE POLICY threads_user_isolation ON threads
    USING (user_id = current_setting('app.user_id', true));

CREATE INDEX threads_user_updated ON threads (user_id, last_updated DESC)
    WHERE is_deleted = FALSE;


-- scheduler — background and foreground agent schedules
CREATE TABLE scheduler (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT        NOT NULL,
    agent_name  TEXT        NOT NULL,           -- e.g. "email-triage", "daily-planner"
    skill       TEXT        NOT NULL,           -- maps to a skill in skills/
    cron        TEXT        NOT NULL,           -- cron expression, e.g. "0 9 * * *"
    next_run    TIMESTAMPTZ NOT NULL,
    last_run    TIMESTAMPTZ,
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    config      JSONB       NOT NULL DEFAULT '{}',  -- agent-specific config
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE scheduler ENABLE ROW LEVEL SECURITY;
CREATE POLICY scheduler_user_isolation ON scheduler
    USING (user_id = current_setting('app.user_id', true));

CREATE UNIQUE INDEX scheduler_user_agent_unique ON scheduler (user_id, agent_name)
    WHERE is_active = TRUE;
CREATE INDEX scheduler_next_run ON scheduler (next_run)
    WHERE is_active = TRUE;


-- notifications — agent → COS delivery queue
CREATE TABLE notifications (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT        NOT NULL,
    from_agent      TEXT        NOT NULL,       -- agent name that produced this
    from_cos_id     TEXT,                       -- set for cross-COS messages (Phase 2+)
    to_thread_id    TEXT,                       -- COS thread to deliver to (NULL = any active)
    message         TEXT        NOT NULL,
    priority        TEXT        NOT NULL DEFAULT 'normal',  -- "urgent", "normal", "low"
    artifact_id     UUID,                       -- optional linked artifact
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    read_at         TIMESTAMPTZ                 -- NULL = unread
);

ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
CREATE POLICY notifications_user_isolation ON notifications
    USING (user_id = current_setting('app.user_id', true));

CREATE INDEX notifications_unread ON notifications (user_id, created_at DESC)
    WHERE read_at IS NULL;


-- artifacts — agent output store
-- Types: "daily_plan", "email_digest", "retro", "financial_summary", etc.
CREATE TABLE artifacts (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT        NOT NULL,
    agent_id    TEXT,                           -- which agent produced this
    type        TEXT        NOT NULL,           -- artifact type
    content     TEXT        NOT NULL,           -- artifact body (markdown, JSON, etc.)
    metadata    JSONB       NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted  BOOLEAN     NOT NULL DEFAULT FALSE
);

ALTER TABLE artifacts ENABLE ROW LEVEL SECURITY;
CREATE POLICY artifacts_user_isolation ON artifacts
    USING (user_id = current_setting('app.user_id', true));

CREATE INDEX artifacts_type_date ON artifacts (user_id, type, created_at DESC)
    WHERE is_deleted = FALSE;


-- cos_trust_registry — cross-COS federation (Phase 2+, schema defined now)
-- Allows two COS instances to share availability/context at a defined trust level.
CREATE TABLE cos_trust_registry (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT        NOT NULL,       -- owner of this trust entry
    cos_id          TEXT        NOT NULL,       -- the trusted COS (e.g. "varun-work")
    trust_level     TEXT        NOT NULL,       -- "availability_only", "context_aware", "full_collaboration"
    granted_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at      TIMESTAMPTZ,               -- NULL = still active
    UNIQUE (user_id, cos_id)
);

ALTER TABLE cos_trust_registry ENABLE ROW LEVEL SECURITY;
CREATE POLICY cos_trust_user_isolation ON cos_trust_registry
    USING (user_id = current_setting('app.user_id', true));


-- user_credentials — per-user OAuth tokens and service credentials
--
-- Stores delegation tokens that authorize the system to act on behalf of a user.
-- token_data is an AES-256 encrypted JSON blob (application-layer encryption;
-- key stored in Azure Key Vault / CREDENTIALS_ENCRYPTION_KEY env var).
--
-- Per-service token_data shapes:
--   google:    {"access_token": "...", "refresh_token": "...", "token_expiry": "...", "scopes": [...]}
--   garmin:    {"garth_tokens": {...}}
--   splitwise: {"api_key": "..."}
--
-- encryption_key_id tracks which key version was used — bump when rotating keys
-- so old rows can be re-encrypted lazily.
CREATE TABLE user_credentials (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             TEXT        NOT NULL,
    service             TEXT        NOT NULL,   -- "google", "garmin", "splitwise", etc.
    token_data          BYTEA       NOT NULL,   -- encrypted JSON blob
    encryption_key_id   TEXT        NOT NULL DEFAULT 'v1',
    expires_at          TIMESTAMPTZ,            -- NULL = non-expiring (e.g. API keys)
    scopes              TEXT[],                 -- OAuth scopes granted
    metadata            JSONB       NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, service)
);

ALTER TABLE user_credentials ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_credentials_isolation ON user_credentials
    USING (user_id = current_setting('app.user_id', true));

CREATE INDEX user_credentials_service ON user_credentials (user_id, service);


-- api_keys — gateway authentication (API key → user_id mapping)
--
-- No RLS on this table — the auth middleware reads it before user_id is known.
-- key_hash is SHA-256 of the raw API key (never store plaintext keys).
CREATE TABLE api_keys (
    key_hash            TEXT        PRIMARY KEY,       -- SHA-256 hex of the raw API key
    user_id             TEXT        NOT NULL,
    profile_name        TEXT        NOT NULL DEFAULT 'personal',
    label               TEXT,                          -- "varun's laptop", "iphone", etc.
    allow_operator_llm  BOOLEAN     NOT NULL DEFAULT FALSE,  -- admin grants fallback to operator LLM key
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used           TIMESTAMPTZ,
    is_revoked          BOOLEAN     NOT NULL DEFAULT FALSE
);

CREATE INDEX api_keys_user_id ON api_keys (user_id);
