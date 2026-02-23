"""
One-time migration: copy thread metadata from SQLite to assistant_system.threads.

Run from agent-orchestrator directory:
    PG_PASSWORD=... python migrations/migrate_threads_to_postgres.py

Safe to re-run — uses INSERT ... ON CONFLICT DO NOTHING.
"""
import os
import sqlite3
import psycopg2
from dotenv import load_dotenv

load_dotenv()

SQLITE_PATH = os.getenv("THREADS_DB", "journal_threads_meta.db")
PG_HOST     = os.getenv("PG_HOST", "journal-db-svarun.postgres.database.azure.com")
PG_USER     = os.getenv("PG_USER", "journaladmin")
PG_PASSWORD = os.getenv("PG_PASSWORD")
USER_ID     = "varun"

# ── Read from SQLite ─────────────────────────────────────────────────────────
src = sqlite3.connect(SQLITE_PATH)
src.row_factory = sqlite3.Row
cur = src.cursor()
cur.execute("""
    SELECT thread_id, title, created_at, last_updated, message_count,
           total_input_tokens, total_output_tokens, mode, target_date,
           model_provider, model_name, is_deleted, emoji
    FROM thread_metadata
""")
rows = cur.fetchall()
src.close()
print(f"Read {len(rows)} threads from SQLite ({SQLITE_PATH})")

# ── Write to PostgreSQL ───────────────────────────────────────────────────────
dst = psycopg2.connect(
    host=PG_HOST, port=5432, dbname="assistant_system",
    user=PG_USER, password=PG_PASSWORD, sslmode="require",
)
dst.autocommit = False
dcur = dst.cursor()

inserted = skipped = 0
for row in rows:
    try:
        dcur.execute("""
            INSERT INTO threads (
                thread_id, user_id, title, created_at, last_updated,
                message_count, total_input_tokens, total_output_tokens,
                mode, target_date, model_provider, model_name, is_deleted, emoji
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (thread_id, user_id) DO NOTHING
        """, (
            row["thread_id"], USER_ID, row["title"],
            row["created_at"], row["last_updated"],
            row["message_count"], row["total_input_tokens"], row["total_output_tokens"],
            row["mode"] or "chat", row["target_date"],
            row["model_provider"], row["model_name"],
            bool(row["is_deleted"]), row["emoji"],
        ))
        if dcur.rowcount > 0:
            inserted += 1
        else:
            skipped += 1
    except Exception as e:
        print(f"  ERROR on {row['thread_id']}: {e}")
        dst.rollback()
        raise

dst.commit()
dst.close()

print(f"Migrated: {inserted} inserted, {skipped} already existed.")

# ── Verify ────────────────────────────────────────────────────────────────────
dst2 = psycopg2.connect(
    host=PG_HOST, port=5432, dbname="assistant_system",
    user=PG_USER, password=PG_PASSWORD, sslmode="require",
)
vcur = dst2.cursor()
vcur.execute("SELECT COUNT(*) FROM threads WHERE user_id = %s", (USER_ID,))
total = vcur.fetchone()[0]
vcur.execute("SELECT COUNT(*) FROM threads WHERE user_id = %s AND message_count > 0", (USER_ID,))
with_msgs = vcur.fetchone()[0]
dst2.close()
print(f"Verified: {total} threads in assistant_system.threads, {with_msgs} with messages.")
