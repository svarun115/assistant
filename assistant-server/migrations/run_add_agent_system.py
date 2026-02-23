"""
Create agent_templates and agent_instances tables in assistant_system.

Run from agent-orchestrator directory:
    python migrations/run_add_agent_system.py
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
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

sql_path = os.path.join(os.path.dirname(__file__), "add_agent_system.sql")
with open(sql_path) as f:
    sql = f.read()

cur.execute(sql)
print("Agent system tables created.")

# Verify
cur.execute("SELECT COUNT(*) FROM agent_templates")
templates = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM agent_instances")
instances = cur.fetchone()[0]
print(f"  agent_templates: {templates} rows")
print(f"  agent_instances: {instances} rows")

cur.close()
conn.close()
print("Done.")
