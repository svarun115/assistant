-- =============================================================================
-- api_keys — API key → user_id mapping for gateway authentication
--
-- Run on assistant_system database:
--   psql "host=... dbname=assistant_system user=journaladmin ..." \
--       -f add_api_keys.sql
--
-- No RLS on this table — middleware reads it before user_id is known.
-- =============================================================================

CREATE TABLE IF NOT EXISTS api_keys (
    key_hash            TEXT        PRIMARY KEY,       -- SHA-256 hex of the raw API key
    user_id             TEXT        NOT NULL,
    profile_name        TEXT        NOT NULL DEFAULT 'personal',
    label               TEXT,                          -- "varun's laptop", "iphone", etc.
    allow_operator_llm  BOOLEAN     NOT NULL DEFAULT FALSE,  -- admin grants fallback to operator LLM key
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used           TIMESTAMPTZ,
    is_revoked          BOOLEAN     NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS api_keys_user_id ON api_keys (user_id);
