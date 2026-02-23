-- =============================================================================
-- Agent system — two-table design for all-DB agent definitions
--
-- agent_templates: shared definitions seeded from agents/ filesystem.
--                  No user ownership. One row per agent name.
--
-- agent_instances: per-user agent state. Content copied from template at
--                  first use, then fully owned by the user (can customize
--                  any file). SOUL always lives here, never in templates.
--
-- Resolution order in AgentLoader:
--   1. agent_instances WHERE user_id=? AND agent_name=? → use directly
--   2. agent_templates WHERE name=? → copy to new instance, return it
--   3. Neither found → AgentNotFoundError
-- =============================================================================

-- ── Templates ────────────────────────────────────────────────────────────────
-- Seeded from agents/ directory on startup by AgentSeeder.sync().
-- Updated when filesystem content changes (detected by content_hash).
-- No user ownership — shared across all users.

CREATE TABLE IF NOT EXISTS agent_templates (
    name            TEXT        PRIMARY KEY,
    description     TEXT        NOT NULL DEFAULT '',
    source          TEXT        NOT NULL DEFAULT 'pre_built',
    -- 'pre_built' | 'imported'

    -- Agent definition files (content of markdown files)
    agent_md        TEXT        NOT NULL,           -- AGENT.md (identity + rules)
    tools_md        TEXT,                           -- TOOLS.md (allowed MCP servers)
    bootstrap_md    TEXT,                           -- BOOTSTRAP.md (session init context)
    heartbeat_md    TEXT,                           -- HEARTBEAT.md (schedules + triggers)

    -- Change detection
    content_hash    TEXT        NOT NULL DEFAULT '',  -- SHA-256 of all content combined
    version         INT         NOT NULL DEFAULT 1,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ── Instances ─────────────────────────────────────────────────────────────────
-- One row per (user_id, agent_name). Created on first use from template,
-- or from scratch for user-defined agents (template_name IS NULL).
--
-- All content fields are fully owned by the user after creation.
-- customized_files tracks which files the user has changed vs. template —
-- upgrade propagation only touches non-customized files.

CREATE TABLE IF NOT EXISTS agent_instances (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             TEXT        NOT NULL,
    agent_name          TEXT        NOT NULL,
    template_name       TEXT,                       -- NULL for user-defined agents
    source              TEXT        NOT NULL,
    -- 'from_template'  → copied from a pre-built template
    -- 'user_defined'   → created by COS at runtime (no template)
    -- 'imported'       → installed from zip/URL

    -- Full agent content (copied from template at creation; user can modify any)
    agent_md            TEXT        NOT NULL,
    tools_md            TEXT,
    bootstrap_md        TEXT,
    heartbeat_md        TEXT,
    soul_md             TEXT,                       -- grows over time; never from template

    -- Tracks which files this user has customized (vs. unmodified template copy)
    -- e.g. '{"agent_md", "heartbeat_md"}' means user changed those two files
    customized_files    TEXT[]      NOT NULL DEFAULT '{}',

    -- Template tracking (for upgrade notifications)
    template_version    INT,                        -- version of template this was created from
    upgrade_available   BOOLEAN     NOT NULL DEFAULT FALSE,  -- set when template is updated

    is_active           BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by          TEXT        NOT NULL DEFAULT 'system',
    -- 'system' | 'cos' | 'user' | 'seeder'

    UNIQUE (user_id, agent_name)
);

ALTER TABLE agent_instances ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_instances_user_isolation ON agent_instances
    USING (user_id = current_setting('app.user_id', true));

-- Indexes
CREATE INDEX IF NOT EXISTS agent_instances_user_active
    ON agent_instances (user_id, agent_name)
    WHERE is_active = TRUE;
