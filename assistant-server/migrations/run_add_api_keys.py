"""
Create api_keys table in assistant_system.

Run from agent-orchestrator directory:
    python migrations/run_add_api_keys.py
"""
import os
import hashlib
import psycopg2
from dotenv import load_dotenv

load_dotenv()
# Also load from db-mcp-server .env.production which has DB_PASSWORD
_db_env = os.path.join(os.path.dirname(__file__), "..", "..", "..", "db-mcp-server", ".env.production")
if os.path.exists(_db_env):
    load_dotenv(_db_env, override=False)

PG_HOST = os.getenv("PG_HOST", os.getenv("DB_HOST", "journal-db-svarun.postgres.database.azure.com"))
PG_USER = os.getenv("PG_USER", os.getenv("DB_USER", "journaladmin"))
PG_PASSWORD = os.getenv("PG_PASSWORD") or os.getenv("DB_PASSWORD")

if not PG_PASSWORD:
    raise RuntimeError("Set PG_PASSWORD or DB_PASSWORD env var")

conn = psycopg2.connect(
    host=PG_HOST, port=5432, dbname="assistant_system",
    user=PG_USER, password=PG_PASSWORD, sslmode="require",
)
conn.autocommit = True
cur = conn.cursor()

# Read and execute the SQL file
sql_path = os.path.join(os.path.dirname(__file__), "add_api_keys.sql")
with open(sql_path) as f:
    sql = f.read()

cur.execute(sql)
print("api_keys table created (or already exists).")

# Auto-seed: if ASSISTANT_API_KEY is set and table is empty, seed for default user
api_key = os.getenv("ASSISTANT_API_KEY")
cur.execute("SELECT COUNT(*) FROM api_keys")
count = cur.fetchone()[0]

if api_key and count == 0:
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    cur.execute("""
        INSERT INTO api_keys (key_hash, user_id, profile_name, label, allow_operator_llm)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (key_hash) DO NOTHING
    """, (key_hash, "varun", "personal", "auto-seeded from ASSISTANT_API_KEY", True))
    print(f"Seeded api_key for user 'varun' (allow_operator_llm=TRUE)")
elif count > 0:
    print(f"api_keys already has {count} row(s), skipping seed.")
else:
    print("No ASSISTANT_API_KEY set, skipping seed.")

# Verify
cur.execute("SELECT LEFT(key_hash, 12) || '...', user_id, profile_name, allow_operator_llm FROM api_keys")
for row in cur.fetchall():
    print(f"  {row}")

cur.close()
conn.close()
print("Done.")
