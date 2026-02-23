"""
One-time script: create assistant_system schema on Azure PostgreSQL.
Run from agent-orchestrator directory.
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

PG_HOST = os.getenv("PG_HOST", "journal-db-svarun.postgres.database.azure.com")
PG_USER = os.getenv("PG_USER", "journaladmin")
PG_PASSWORD = os.getenv("PG_PASSWORD")
PG_SSL = "require"

conn = psycopg2.connect(
    host=PG_HOST,
    port=5432,
    dbname="assistant_system",
    user=PG_USER,
    password=PG_PASSWORD,
    sslmode=PG_SSL,
)
conn.autocommit = True
cur = conn.cursor()

statements = [
    """
    CREATE TABLE IF NOT EXISTS threads (
        thread_id           TEXT        NOT NULL,
        user_id             TEXT        NOT NULL DEFAULT 'varun',
        title               TEXT        NOT NULL DEFAULT 'New Conversation',
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_updated        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        message_count       INT         NOT NULL DEFAULT 0,
        total_input_tokens  BIGINT      NOT NULL DEFAULT 0,
        total_output_tokens BIGINT      NOT NULL DEFAULT 0,
        mode                TEXT        NOT NULL DEFAULT 'chat',
        target_date         DATE,
        model_provider      TEXT,
        model_name          TEXT,
        is_deleted          BOOLEAN     NOT NULL DEFAULT FALSE,
        emoji               TEXT,
        PRIMARY KEY (thread_id, user_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS threads_user_updated
        ON threads (user_id, last_updated DESC)
        WHERE is_deleted = FALSE
    """,
    """
    CREATE TABLE IF NOT EXISTS scheduler (
        id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id     TEXT        NOT NULL,
        agent_name  TEXT        NOT NULL,
        skill       TEXT        NOT NULL,
        cron        TEXT        NOT NULL,
        next_run    TIMESTAMPTZ NOT NULL,
        last_run    TIMESTAMPTZ,
        is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
        config      JSONB       NOT NULL DEFAULT '{}',
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS scheduler_next_run
        ON scheduler (next_run)
        WHERE is_active = TRUE
    """,
    """
    CREATE TABLE IF NOT EXISTS notifications (
        id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id         TEXT        NOT NULL,
        from_agent      TEXT        NOT NULL,
        from_cos_id     TEXT,
        to_thread_id    TEXT,
        message         TEXT        NOT NULL,
        priority        TEXT        NOT NULL DEFAULT 'normal',
        artifact_id     UUID,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        read_at         TIMESTAMPTZ
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS notifications_unread
        ON notifications (user_id, created_at DESC)
        WHERE read_at IS NULL
    """,
    """
    CREATE TABLE IF NOT EXISTS artifacts (
        id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id     TEXT        NOT NULL,
        agent_id    TEXT,
        type        TEXT        NOT NULL,
        content     TEXT        NOT NULL,
        metadata    JSONB       NOT NULL DEFAULT '{}',
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        is_deleted  BOOLEAN     NOT NULL DEFAULT FALSE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS artifacts_type_date
        ON artifacts (user_id, type, created_at DESC)
        WHERE is_deleted = FALSE
    """,
    """
    CREATE TABLE IF NOT EXISTS cos_trust_registry (
        id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id     TEXT        NOT NULL,
        cos_id      TEXT        NOT NULL,
        trust_level TEXT        NOT NULL,
        granted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        revoked_at  TIMESTAMPTZ,
        UNIQUE (user_id, cos_id)
    )
    """,
]

for i, stmt in enumerate(statements):
    cur.execute(stmt)
    print(f"  [{i+1}/{len(statements)}] OK")

cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;")
tables = [r[0] for r in cur.fetchall()]
print(f"\nassistant_system tables: {tables}")
conn.close()
print("Done.")
