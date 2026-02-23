"""
AgentLoader + AgentSeeder — all-DB agent definition system with system-agent support.

Two agent categories:

1. USER AGENTS (COS, financial-advisor, fitness-coach, user-defined)
   - agent_templates: shared definitions seeded from agents/ (setup only, not runtime)
   - agent_instances: per-user rows with mutable SOUL and optional customizations
   - Resolution: instances → templates → AgentNotFoundError

2. SYSTEM AGENTS (Architect, future: Monitor, Auditor)
   - Lives in system-agents/ directory (ships with Docker image)
   - Service-level: same for all users, no soul, no per-user instances
   - Access-controlled: access field in AGENT.md frontmatter
     - cos_internal: invokable by COS as internal task agent
     - admin_direct: directly invokable by admin-role users (profile_name='admin')
   - Resolution: agent_instances → agent_templates → system-agents/ → error

Resolution order (AgentLoader.resolve):
  1. agent_instances (user_id, agent_name) → return directly
  2. agent_templates (name) → copy to new per-user instance, return it
  3. system-agents/{name}/ → read from filesystem, enforce access rules, return
  4. None found → AgentNotFoundError

Admin role: api_keys.profile_name = 'admin' grants direct access to system agents.
Regular users (profile_name = 'personal') can only reach system agents via COS internal calls.

Usage:
    loader = AgentLoader(auth_pool)

    # Get agent definition for a user (creates instance on first use for user agents)
    definition = await loader.resolve("financial-advisor", user_id="varun")

    # Get agent definition for a user (creates instance on first use)
    definition = await loader.resolve("financial-advisor", user_id="varun")
    print(definition.agent_md)      # identity prompt
    print(definition.allowed_servers)  # from tools_md

    # Update soul after a session
    await loader.append_soul("financial-advisor", "varun",
        "2026-02-22: User confirmed to hold off rebalancing until March.")

    # COS creates a new agent
    agent_name = await loader.create(
        user_id="varun",
        agent_name="reading-habit",
        agent_md="You track the user's daily reading habit...",
        tools_md="allowed_servers: [journal-db]",
        heartbeat_md='''---
schedules:
  - name: daily-check
    cron: "30 14 * * *"
    task: "Check if reading was logged today. Post reminder if not."
    artifact_type: reading_reminder
---''',
    )
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import yaml

logger = logging.getLogger(__name__)

# Default tools_md content when no TOOLS.md exists (unrestricted)
_DEFAULT_TOOLS_MD = "allowed_servers: []  # unrestricted"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class AgentDefinition:
    """Resolved agent definition for a specific user."""
    agent_name: str
    user_id: str
    source: str                         # 'from_template' | 'user_defined' | 'imported'
    agent_md: str                       # identity + rules
    tools_md: Optional[str]             # allowed MCP servers
    bootstrap_md: Optional[str]         # session init context
    heartbeat_md: Optional[str]         # schedules + triggers
    soul_md: Optional[str]              # persistent memory
    customized_files: list[str]         # files the user has modified
    template_version: Optional[int]
    upgrade_available: bool

    @property
    def allowed_servers(self) -> Optional[list[str]]:
        """Parse allowed_servers from tools_md YAML. None = unrestricted."""
        if not self.tools_md:
            return None
        try:
            data = _parse_yaml_frontmatter(self.tools_md) or yaml.safe_load(self.tools_md) or {}
            servers = data.get("allowed_servers")
            if servers == [] or servers is None:
                return None   # empty list = unrestricted
            return servers
        except Exception:
            return None

    @property
    def schedules(self) -> list[dict]:
        """Parse schedule declarations from heartbeat_md YAML frontmatter."""
        if not self.heartbeat_md:
            return []
        data = _parse_yaml_frontmatter(self.heartbeat_md)
        return data.get("schedules", [])

    @property
    def triggers(self) -> list[dict]:
        """Parse proactive trigger declarations from heartbeat_md."""
        if not self.heartbeat_md:
            return []
        data = _parse_yaml_frontmatter(self.heartbeat_md)
        return data.get("triggers", [])

    def get_system_prompt(self) -> str:
        """Build system prompt: agent_md + soul context."""
        parts = [self.agent_md]
        if self.soul_md and self.soul_md.strip():
            parts.append("\n\n---\n## Your Memory (past sessions)\n\n" + self.soul_md)
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# YAML frontmatter parser
# ---------------------------------------------------------------------------

def _parse_yaml_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter (between --- delimiters) from a markdown file."""
    if not content:
        return {}
    match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return {}
    try:
        return yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as e:
        logger.warning(f"Failed to parse YAML frontmatter: {e}")
        return {}


def _content_hash(agent_md: str, tools_md: str = "", bootstrap_md: str = "",
                  heartbeat_md: str = "") -> str:
    """SHA-256 of all agent content combined."""
    combined = "\n".join([agent_md or "", tools_md or "", bootstrap_md or "", heartbeat_md or ""])
    return hashlib.sha256(combined.encode()).hexdigest()


# ---------------------------------------------------------------------------
# AgentSeeder — filesystem → agent_templates
# ---------------------------------------------------------------------------

class AgentSeeder:
    """
    One-way sync: agents/ directory → assistant_system.agent_templates.

    Reads each subdirectory in agents_dir, looks for:
      AGENT.md      (required)
      TOOLS.md      (optional)
      BOOTSTRAP.md  (optional)
      HEARTBEAT.md  (optional)

    Also accepts SKILL.md (Claude Code compat) as AGENT.md equivalent.

    Upserts into agent_templates. Updates version + sets upgrade_available=TRUE
    on affected instances when content changes.
    """

    def __init__(self, pg_pool, agents_dir: Path):
        self._pool = pg_pool
        self._agents_dir = agents_dir

    async def sync(self) -> dict[str, str]:
        """
        Sync all agent directories into agent_templates.

        Returns dict of {name: 'created'|'updated'|'unchanged'}.
        """
        if not self._agents_dir.exists():
            logger.warning(f"AgentSeeder: agents_dir does not exist: {self._agents_dir}")
            return {}

        results = {}
        for agent_dir in sorted(self._agents_dir.iterdir()):
            if not agent_dir.is_dir():
                continue
            name = agent_dir.name
            try:
                status = await self._sync_one(name, agent_dir)
                results[name] = status
                if status != "unchanged":
                    logger.info(f"AgentSeeder: {name} → {status}")
            except Exception as e:
                logger.error(f"AgentSeeder: failed to sync {name}: {e}", exc_info=True)
                results[name] = "error"

        logger.info(f"AgentSeeder: synced {len(results)} agents: "
                    f"{sum(1 for v in results.values() if v == 'created')} created, "
                    f"{sum(1 for v in results.values() if v == 'updated')} updated")
        return results

    async def _sync_one(self, name: str, agent_dir: Path) -> str:
        """Sync a single agent directory. Returns 'created'|'updated'|'unchanged'."""
        # Read files
        agent_md = _read_file(agent_dir / "AGENT.md") or _read_file(agent_dir / "SKILL.md")
        if not agent_md:
            logger.debug(f"AgentSeeder: skipping {name} — no AGENT.md or SKILL.md")
            return "skipped"

        tools_md = _read_file(agent_dir / "TOOLS.md")
        bootstrap_md = _read_file(agent_dir / "BOOTSTRAP.md")
        heartbeat_md = _read_file(agent_dir / "HEARTBEAT.md")

        # Extract description from frontmatter or first line
        description = _extract_description(agent_md)
        new_hash = _content_hash(agent_md, tools_md or "", bootstrap_md or "", heartbeat_md or "")

        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "SELECT content_hash, version FROM agent_templates WHERE name = %s",
                (name,),
            )
            existing = await cur.fetchone()

            if existing is None:
                # Insert new template
                await conn.execute(
                    """INSERT INTO agent_templates
                       (name, description, agent_md, tools_md, bootstrap_md, heartbeat_md, content_hash, version)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, 1)""",
                    (name, description, agent_md, tools_md, bootstrap_md, heartbeat_md, new_hash),
                )
                return "created"

            old_hash, old_version = existing
            if old_hash == new_hash:
                return "unchanged"

            # Update template + bump version
            new_version = old_version + 1
            await conn.execute(
                """UPDATE agent_templates SET
                   description=%s, agent_md=%s, tools_md=%s, bootstrap_md=%s,
                   heartbeat_md=%s, content_hash=%s, version=%s, updated_at=NOW()
                   WHERE name=%s""",
                (description, agent_md, tools_md, bootstrap_md, heartbeat_md,
                 new_hash, new_version, name),
            )
            # Flag instances that haven't been customized for upgrade availability
            await conn.execute(
                """UPDATE agent_instances SET upgrade_available=TRUE
                   WHERE template_name=%s AND NOT ('agent_md' = ANY(customized_files))""",
                (name,),
            )
            return "updated"

    async def sync_skill(self, skill_path: Path, name: Optional[str] = None) -> str:
        """
        Import a Claude Code SKILL.md as an agent template.

        skill_path: path to the skill directory (containing SKILL.md)
        name: agent name override (defaults to directory name)
        """
        agent_name = name or skill_path.name
        return await self._sync_one(agent_name, skill_path)


# ---------------------------------------------------------------------------
# AgentLoader — the runtime resolver
# ---------------------------------------------------------------------------

class AgentLoader:
    """
    Resolves agent definitions for a specific user.

    Resolution order:
      1. agent_instances (user_id, agent_name) → return directly
      2. agent_templates (name) → copy to new per-user instance
      3. system-agents/{name}/ → filesystem, access-controlled (cos_internal or admin_direct)
      4. Neither → AgentNotFoundError

    system_agents_dir: path to system-agents/ (ships with Docker image).
    Defaults to {parent of this file}/system-agents.
    """

    # Caller profiles that can invoke cos_internal system agents
    COS_INTERNAL_PROFILE = "cos_internal"
    ADMIN_PROFILE = "admin"

    def __init__(self, pg_pool, agents_dir: Optional[Path] = None, system_agents_dir: Optional[Path] = None):
        self._pool = pg_pool
        self.seeder = AgentSeeder(pg_pool, agents_dir or Path("agents"))
        self._system_agents_dir = system_agents_dir or (Path(__file__).parent / "system-agents")

    async def resolve(
        self,
        agent_name: str,
        user_id: str,
        caller_profile: str = "personal",
    ) -> AgentDefinition:
        """
        Get the AgentDefinition for this user. Creates instance on first use.

        For system agents (in system-agents/ dir), enforces access rules:
          - cos_internal callers: can invoke agents with 'cos_internal' access
          - admin callers (caller_profile='admin'): can invoke 'admin_direct' agents
          - regular users (caller_profile='personal'): no system agent access

        Args:
            agent_name: name of the agent to resolve.
            user_id: requesting user's ID.
            caller_profile: 'personal' | 'admin' | 'cos_internal'.

        Raises:
            AgentNotFoundError: no agent found anywhere.
            AgentAccessDeniedError: found a system agent but caller lacks access.
        """
        async with self._pool.connection() as conn:
            # 1. Check for existing user instance
            cur = await conn.execute(
                """SELECT agent_md, tools_md, bootstrap_md, heartbeat_md, soul_md,
                          source, customized_files, template_version, upgrade_available
                   FROM agent_instances
                   WHERE user_id=%s AND agent_name=%s AND is_active=TRUE""",
                (user_id, agent_name),
            )
            row = await cur.fetchone()

        if row:
            return AgentDefinition(
                agent_name=agent_name,
                user_id=user_id,
                source=row[5],
                agent_md=row[0],
                tools_md=row[1],
                bootstrap_md=row[2],
                heartbeat_md=row[3],
                soul_md=row[4],
                customized_files=row[6] or [],
                template_version=row[7],
                upgrade_available=row[8],
            )

        # 2. No instance — check template and create instance
        try:
            return await self._create_instance_from_template(agent_name, user_id)
        except AgentNotFoundError:
            pass

        # 3. Check system-agents/ directory (service-level, access-controlled)
        return self._resolve_system_agent(agent_name, caller_profile)

    def _resolve_system_agent(self, agent_name: str, caller_profile: str) -> "AgentDefinition":
        """
        Load a system agent from the system-agents/ filesystem directory.

        Access rules from AGENT.md frontmatter 'access' list:
          cos_internal  → any caller_profile accepted (COS internal trust)
          admin_direct  → requires caller_profile == 'admin'

        Regular users (profile='personal') cannot access system agents.
        """
        agent_dir = self._system_agents_dir / agent_name
        if not agent_dir.is_dir():
            raise AgentNotFoundError(f"No agent found: '{agent_name}'")

        agent_md = _read_file(agent_dir / "AGENT.md")
        if not agent_md:
            raise AgentNotFoundError(f"System agent '{agent_name}' has no AGENT.md")

        # Parse access rules from frontmatter
        frontmatter = _parse_yaml_frontmatter(agent_md)
        access_rules = frontmatter.get("access", [])
        if isinstance(access_rules, str):
            access_rules = [access_rules]

        # Enforce access
        allowed = False
        if caller_profile == self.COS_INTERNAL_PROFILE and "cos_internal" in access_rules:
            allowed = True
        elif caller_profile == self.ADMIN_PROFILE and "admin_direct" in access_rules:
            allowed = True
        elif caller_profile == self.ADMIN_PROFILE and "cos_internal" in access_rules:
            # Admins can also use cos_internal agents
            allowed = True

        if not allowed:
            raise AgentAccessDeniedError(
                f"Agent '{agent_name}' requires "
                f"{access_rules} access. Caller profile: '{caller_profile}'"
            )

        # Load all files
        tools_md = _read_file(agent_dir / "TOOLS.md")
        bootstrap_md = _read_file(agent_dir / "BOOTSTRAP.md")

        # Load doc index from docs/ subdirectory if present
        docs_dir = agent_dir / "docs"
        doc_index = None
        if docs_dir.is_dir():
            doc_files = sorted(docs_dir.glob("*.md"))
            if doc_files:
                doc_parts = [f"# Reference: {f.stem}\n\n{f.read_text(encoding='utf-8').strip()}" for f in doc_files]
                doc_index = "\n\n---\n\n".join(doc_parts)

        # Combine bootstrap + doc index for complete context
        full_bootstrap = bootstrap_md or ""
        if doc_index:
            full_bootstrap = f"{full_bootstrap}\n\n---\n\n{doc_index}" if full_bootstrap else doc_index

        logger.debug(f"Resolved system agent '{agent_name}' for caller_profile='{caller_profile}'")

        return AgentDefinition(
            agent_name=agent_name,
            user_id="__system__",
            source="system",
            agent_md=agent_md,
            tools_md=tools_md,
            bootstrap_md=full_bootstrap,
            heartbeat_md=None,   # system agents don't self-schedule
            soul_md=None,        # system agents have no soul — they have reference docs
            customized_files=[],
            template_version=None,
            upgrade_available=False,
        )

    async def _create_instance_from_template(self, agent_name: str, user_id: str) -> AgentDefinition:
        """Copy template into a new user instance."""
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                """SELECT agent_md, tools_md, bootstrap_md, heartbeat_md, version
                   FROM agent_templates WHERE name=%s""",
                (agent_name,),
            )
            template = await cur.fetchone()

        if not template:
            raise AgentNotFoundError(f"No agent template found for '{agent_name}'")

        agent_md, tools_md, bootstrap_md, heartbeat_md, version = template

        async with self._pool.connection() as conn:
            await conn.execute(
                """INSERT INTO agent_instances
                   (user_id, agent_name, template_name, source,
                    agent_md, tools_md, bootstrap_md, heartbeat_md,
                    template_version, created_by)
                   VALUES (%s, %s, %s, 'from_template', %s, %s, %s, %s, %s, 'seeder')
                   ON CONFLICT (user_id, agent_name) DO NOTHING""",
                (user_id, agent_name, agent_name, agent_md, tools_md,
                 bootstrap_md, heartbeat_md, version),
            )

        logger.info(f"AgentLoader: created instance '{agent_name}' for user '{user_id}' from template v{version}")

        return AgentDefinition(
            agent_name=agent_name,
            user_id=user_id,
            source="from_template",
            agent_md=agent_md,
            tools_md=tools_md,
            bootstrap_md=bootstrap_md,
            heartbeat_md=heartbeat_md,
            soul_md=None,
            customized_files=[],
            template_version=version,
            upgrade_available=False,
        )

    async def append_soul(self, agent_name: str, user_id: str, entry: str) -> None:
        """Append a dated memory entry to the user's agent soul_md."""
        from datetime import date
        dated_entry = f"\n{date.today().isoformat()}: {entry.strip()}"
        async with self._pool.connection() as conn:
            await conn.execute(
                """UPDATE agent_instances
                   SET soul_md = COALESCE(soul_md, '') || %s,
                       updated_at = NOW()
                   WHERE user_id=%s AND agent_name=%s""",
                (dated_entry, user_id, agent_name),
            )

    async def update_file(
        self, agent_name: str, user_id: str,
        file: str, content: str,
    ) -> None:
        """
        Update a specific file on the user's agent instance.

        file: one of 'agent_md', 'tools_md', 'bootstrap_md', 'heartbeat_md', 'soul_md'
        Marks the file as customized (won't be overwritten by template upgrades).
        """
        valid_files = {"agent_md", "tools_md", "bootstrap_md", "heartbeat_md", "soul_md"}
        if file not in valid_files:
            raise ValueError(f"Unknown agent file: {file}. Must be one of {valid_files}")

        async with self._pool.connection() as conn:
            await conn.execute(
                f"""UPDATE agent_instances
                    SET {file} = %s,
                        customized_files = array_append(
                            array_remove(customized_files, %s::text), %s::text
                        ),
                        updated_at = NOW()
                    WHERE user_id=%s AND agent_name=%s""",
                (content, file, file, user_id, agent_name),
            )
        logger.info(f"AgentLoader: updated '{file}' for '{agent_name}' / '{user_id}'")

    async def create(
        self,
        user_id: str,
        agent_name: str,
        agent_md: str,
        tools_md: Optional[str] = None,
        bootstrap_md: Optional[str] = None,
        heartbeat_md: Optional[str] = None,
        created_by: str = "cos",
    ) -> str:
        """
        Create a new user-defined agent (no template). Called by COS.

        Returns agent_name.
        """
        async with self._pool.connection() as conn:
            await conn.execute(
                """INSERT INTO agent_instances
                   (user_id, agent_name, template_name, source,
                    agent_md, tools_md, bootstrap_md, heartbeat_md, created_by)
                   VALUES (%s, %s, NULL, 'user_defined', %s, %s, %s, %s, %s)
                   ON CONFLICT (user_id, agent_name) DO UPDATE SET
                       agent_md=EXCLUDED.agent_md,
                       tools_md=EXCLUDED.tools_md,
                       bootstrap_md=EXCLUDED.bootstrap_md,
                       heartbeat_md=EXCLUDED.heartbeat_md,
                       updated_at=NOW()""",
                (user_id, agent_name, agent_md, tools_md, bootstrap_md, heartbeat_md, created_by),
            )
        logger.info(f"AgentLoader: created user-defined agent '{agent_name}' for '{user_id}'")
        return agent_name

    async def delete(self, agent_name: str, user_id: str) -> bool:
        """Soft-delete a user's agent instance."""
        async with self._pool.connection() as conn:
            result = await conn.execute(
                "UPDATE agent_instances SET is_active=FALSE, updated_at=NOW() "
                "WHERE user_id=%s AND agent_name=%s AND is_active=TRUE",
                (user_id, agent_name),
            )
            return result.rowcount > 0

    async def list_agents(self, user_id: str) -> list[dict]:
        """List all active agents for a user (instances + available templates without instances)."""
        async with self._pool.connection() as conn:
            # User's existing instances
            cur = await conn.execute(
                """SELECT agent_name, source, template_name, upgrade_available, created_at
                   FROM agent_instances WHERE user_id=%s AND is_active=TRUE ORDER BY agent_name""",
                (user_id,),
            )
            instances = {row[0]: row for row in await cur.fetchall()}

            # All available templates (not yet instantiated by this user)
            cur = await conn.execute(
                "SELECT name, description FROM agent_templates ORDER BY name"
            )
            templates = await cur.fetchall()

        result = []
        for name, description in templates:
            if name in instances:
                row = instances[name]
                result.append({
                    "name": name,
                    "description": description,
                    "source": row[1],
                    "has_instance": True,
                    "upgrade_available": row[3],
                    "created_at": row[4].isoformat(),
                })
            else:
                result.append({
                    "name": name,
                    "description": description,
                    "source": "template_available",
                    "has_instance": False,
                    "upgrade_available": False,
                })
        # User-defined agents (no template)
        for name, row in instances.items():
            if row[2] is None:  # no template_name
                result.append({
                    "name": name,
                    "description": "(user-defined)",
                    "source": "user_defined",
                    "has_instance": True,
                    "upgrade_available": False,
                    "created_at": row[4].isoformat(),
                })
        return result

    async def get_all_schedules(self, user_id: str) -> list[dict]:
        """
        Get all schedule declarations from all active agent instances for a user.

        Returns list of schedule dicts with 'agent_name' added.
        Used by AgentScheduler.sync_from_heartbeats().
        """
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "SELECT agent_name, heartbeat_md FROM agent_instances "
                "WHERE user_id=%s AND is_active=TRUE AND heartbeat_md IS NOT NULL",
                (user_id,),
            )
            rows = await cur.fetchall()

        schedules = []
        for agent_name, heartbeat_md in rows:
            data = _parse_yaml_frontmatter(heartbeat_md)
            for sched in data.get("schedules", []):
                schedules.append({**sched, "agent_name": f"{agent_name}-{sched['name']}"
                                   if "name" in sched else agent_name,
                                   "skill": agent_name})
        return schedules

    async def get_all_triggers(self, user_id: str) -> list[dict]:
        """Get all proactive trigger declarations from all active agent instances."""
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                "SELECT agent_name, heartbeat_md FROM agent_instances "
                "WHERE user_id=%s AND is_active=TRUE AND heartbeat_md IS NOT NULL",
                (user_id,),
            )
            rows = await cur.fetchall()

        triggers = []
        for agent_name, heartbeat_md in rows:
            data = _parse_yaml_frontmatter(heartbeat_md)
            for trigger in data.get("triggers", []):
                triggers.append({**trigger, "source_agent": agent_name})
        return triggers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class AgentNotFoundError(Exception):
    pass


class AgentAccessDeniedError(Exception):
    pass


def _read_file(path: Path) -> Optional[str]:
    """Read a file if it exists, return None otherwise."""
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return None


def _extract_description(agent_md: str) -> str:
    """Extract description from YAML frontmatter 'description' field."""
    data = _parse_yaml_frontmatter(agent_md)
    desc = data.get("description", "")
    if desc:
        return desc
    # Fall back to first non-empty line after the frontmatter
    lines = agent_md.split("\n")
    for line in lines:
        line = line.strip().lstrip("#").strip()
        if line and not line.startswith("---") and not line.startswith("name:"):
            return line[:200]
    return ""
