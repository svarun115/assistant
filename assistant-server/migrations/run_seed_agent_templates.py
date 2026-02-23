"""
Seed agent templates from the agents/ directory into assistant_system.agent_templates.

Run from agent-orchestrator directory:
    python migrations/run_seed_agent_templates.py

Safe to re-run — uses INSERT ... ON CONFLICT DO UPDATE when content changes.
"""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

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

AGENTS_DIR = Path(__file__).parent.parent / "agents"


def read_file(path: Path):
    return path.read_text(encoding="utf-8").strip() if path.exists() else None


def extract_description(agent_md: str) -> str:
    """Pull description from YAML frontmatter."""
    if not agent_md:
        return ""
    match = re.match(r'^---\s*\n(.*?)\n---', agent_md, re.DOTALL)
    if match:
        import re as _re
        desc_match = _re.search(r'^description:\s*(.+)$', match.group(1), re.MULTILINE)
        if desc_match:
            return desc_match.group(1).strip().strip('"\'')
    return ""


def content_hash(*parts) -> str:
    combined = "\n".join(p or "" for p in parts)
    return hashlib.sha256(combined.encode()).hexdigest()


if not AGENTS_DIR.exists():
    print(f"ERROR: agents/ directory not found at {AGENTS_DIR}")
    sys.exit(1)

created = updated = unchanged = 0

for agent_dir in sorted(AGENTS_DIR.iterdir()):
    if not agent_dir.is_dir():
        continue
    name = agent_dir.name
    agent_md = read_file(agent_dir / "AGENT.md") or read_file(agent_dir / "SKILL.md")
    if not agent_md:
        print(f"  SKIP {name} — no AGENT.md or SKILL.md")
        continue

    tools_md     = read_file(agent_dir / "TOOLS.md")
    bootstrap_md = read_file(agent_dir / "BOOTSTRAP.md")
    heartbeat_md = read_file(agent_dir / "HEARTBEAT.md")
    description  = extract_description(agent_md)
    new_hash     = content_hash(agent_md, tools_md, bootstrap_md, heartbeat_md)

    cur.execute("SELECT content_hash, version FROM agent_templates WHERE name = %s", (name,))
    existing = cur.fetchone()

    if existing is None:
        cur.execute(
            """INSERT INTO agent_templates
               (name, description, agent_md, tools_md, bootstrap_md, heartbeat_md, content_hash, version)
               VALUES (%s, %s, %s, %s, %s, %s, %s, 1)""",
            (name, description, agent_md, tools_md, bootstrap_md, heartbeat_md, new_hash),
        )
        print(f"  CREATED  {name}")
        created += 1
    elif existing[0] != new_hash:
        new_version = existing[1] + 1
        cur.execute(
            """UPDATE agent_templates SET
               description=%s, agent_md=%s, tools_md=%s, bootstrap_md=%s,
               heartbeat_md=%s, content_hash=%s, version=%s, updated_at=NOW()
               WHERE name=%s""",
            (description, agent_md, tools_md, bootstrap_md, heartbeat_md, new_hash, new_version, name),
        )
        # Flag user instances for upgrade (non-customized files)
        cur.execute(
            "UPDATE agent_instances SET upgrade_available=TRUE "
            "WHERE template_name=%s AND NOT ('agent_md' = ANY(customized_files))",
            (name,),
        )
        print(f"  UPDATED  {name}  (v{existing[1]} -> v{new_version})")
        updated += 1
    else:
        print(f"  ok       {name}  (unchanged)")
        unchanged += 1

cur.close()
conn.close()
print(f"\nDone: {created} created, {updated} updated, {unchanged} unchanged.")

# Verify
conn2 = psycopg2.connect(
    host=PG_HOST, port=5432, dbname="assistant_system",
    user=PG_USER, password=PG_PASSWORD, sslmode="require",
)
cur2 = conn2.cursor()
cur2.execute("SELECT name, version, LEFT(content_hash,12) FROM agent_templates ORDER BY name")
rows = cur2.fetchall()
print(f"\n{len(rows)} agent template(s) in DB:")
for r in rows:
    print(f"  {r[0]:25s}  v{r[1]}  {r[2]}...")

cur2.execute(
    "SELECT agent_name, source, soul_md IS NOT NULL as has_soul FROM agent_instances WHERE user_id = %s ORDER BY agent_name",
    (SYSTEM_USER_ID,)
)
instances = cur2.fetchall()
if instances:
    print(f"\n{len(instances)} agent instance(s) for '{SYSTEM_USER_ID}':")
    for r in instances:
        print(f"  {r[0]:25s}  source={r[1]}  soul={'yes' if r[2] else 'no'}")
cur2.close()
conn2.close()
