"""
Skills Loader — loads skill system prompts from ~/.claude/skills/.

Each skill is a directory with a SKILL.md (main entry point) and optional
supporting files (logging.md, entities.md, etc.) that are combined at load time.

The skills/ directory is a symlink to ~/.claude/skills/ — single source of truth
shared between Claude Code and journal-processor.
"""

import logging
import json
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# Base behavior prompt — generic assistant rules, no user-specific info.
# User identity comes from user-context.md (injected at runtime).
BASE_SYSTEM_PROMPT = """You are a personal assistant — warm, precise, and helpful.

## Core Behaviors
- Be conversational and supportive, never robotic
- Prioritize data integrity over speed
- Ask clarifying questions when needed, but limit to 1-3 per turn (prefer 1)
- Never invent facts, times, locations, or people — ask if unsure
- Always search before creating entities to prevent duplicates

## Query Strategy: SQL First
For factual questions (counts, dates, frequency, participants, locations), use SQL first:
- "How many times did I play tennis?" → SQL SELECT COUNT(*)
- "When did I last run?" → SQL SELECT start_time ORDER BY DESC LIMIT 1

Only use semantic search (search_journal_history) for:
- Mood/feeling questions: "How have I been feeling?"
- Story/context questions: "Tell me about that trip..."

SQL is fast and precise. Semantic search returns large chunks that consume tokens.

## Critical Schema Reference
Key tables (use EXACT names in SQL):
- people: id, canonical_name, aliases (text[]), relationship, category
- locations: id, canonical_name, place_id, location_type, notes
- events: id, event_type, title, start_time, end_time, location_id, category, notes, is_deleted
- workouts: id, event_id, workout_name, category (NOT workout_type!), sport_type
- meals: id, event_id, meal_title, meal_type
- journal_entries: raw_text (NOT entry_text), entry_date
- event_participants: event_id → events.id, person_id → people.id
- person_notes: person_id → people.id, note_type, text

Soft delete: use COALESCE(is_deleted, false) = false
"""


# Maps slash command name → skills/ subdirectory name
# (all lowercase, matches ~/.claude/skills/ directory names)
SKILL_MAP = {
    "cos":              "cos",              # Chief of Staff — primary orchestrator
    "journal":          "journal",
    "daily-tracker":    "daily-tracker",
    "email-triage":     "email-triage",
    "expenses":         "expenses",
    "financial-advisor": "financial-advisor",
    "fitness-coach":    "fitness-coach",
    "retro":            "retro",
    "done":             "done",
    "kusto":            "kusto",
    "create-ado":       "create-ado",
}

# Files to load alongside SKILL.md for each skill + mode
# Keys: (skill_name, mode) where mode is None for always-include
SKILL_SUPPORT_FILES = {
    ("journal", "logging"):  ["logging.md", "entities.md", "gotchas.md"],
    ("journal", "querying"): ["entities.md", "gotchas.md"],
    ("journal", "reflecting"):["reflection.md"],
    ("journal", None):       ["entities.md"],
    ("daily-tracker", None): ["skill.md"],  # daily-tracker uses skill.md not SKILL.md
}

# Main skill filename per skill (most use SKILL.md, daily-tracker uses skill.md)
SKILL_MAIN_FILE = {
    "daily-tracker": "skill.md",
}

# MCP servers each skill is allowed to access.
# None means unrestricted (all connected servers).
# "_internal" (expand_reference) is always included automatically.
SKILL_ALLOWED_SERVERS: dict[str, list[str] | None] = {
    # COS has access to all servers — it's the orchestrator
    "cos":              None,
    "journal":          ["journal-db", "garmin", "google-places"],
    "daily-tracker":    ["journal-db", "garmin", "google-places", "google-workspace"],
    "email-triage":     ["google-workspace", "journal-db"],
    "expenses":         ["splitwise", "google-workspace", "journal-db"],
    "financial-advisor":["journal-db", "google-workspace"],
    "fitness-coach":    ["garmin", "journal-db"],
    "retro":            ["journal-db"],
    "done":             ["journal-db"],
    "kusto":            None,   # kusto MCP not in current config — unrestricted fallback
    "create-ado":       None,   # ADO MCP not in current config — unrestricted fallback
}


class SkillsLoader:
    """
    Loads skill content from ~/.claude/skills/ (via symlink at agent-orchestrator/skills/).

    Usage:
        loader = SkillsLoader()
        content = loader.load_skill_content("journal", mode="logging")
        base = loader.get_base_prompt()
    """

    def __init__(self, skills_dir: Optional[Path] = None, data_dir: Optional[Path] = None):
        if skills_dir:
            self.skills_dir = Path(skills_dir)
        else:
            candidates = [
                Path(__file__).parent / "skills",
                Path("skills"),
                Path("agent-orchestrator/skills"),
            ]
            self.skills_dir = next(
                (c.resolve() for c in candidates if c.exists()), None
            )

        # data_dir: where user-context.md and daily-context.json live.
        # If not provided, load_user_context/load_daily_context fall back to ~/.claude/data.
        self.data_dir: Optional[Path] = Path(data_dir) if data_dir else None

        self._cache: dict[str, str] = {}

        if self.skills_dir:
            logger.info(f"Skills directory: {self.skills_dir}")
        else:
            logger.warning("Skills directory not found — using base prompt only")

    def get_base_prompt(self) -> str:
        return BASE_SYSTEM_PROMPT

    def _read_file(self, path: Path) -> Optional[str]:
        """Read a file and strip YAML frontmatter if present."""
        if not path.exists():
            return None
        try:
            content = path.read_text(encoding="utf-8")
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    content = parts[2].strip()
            return content
        except Exception as e:
            logger.error(f"Error reading {path}: {e}")
            return None

    def load_skill_content(self, skill_name: str, mode: Optional[str] = None) -> str:
        """
        Load the main SKILL.md for a skill plus any mode-appropriate support files.

        Args:
            skill_name: Slash command name (e.g., "journal", "daily-tracker")
            mode: Current mode within the skill (e.g., "logging", "querying")

        Returns:
            Combined skill content ready to inject as system prompt context.
        """
        cache_key = f"{skill_name}:{mode}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not self.skills_dir:
            return ""

        dir_name = SKILL_MAP.get(skill_name, skill_name)
        skill_dir = self.skills_dir / dir_name

        if not skill_dir.exists():
            logger.warning(f"Skill directory not found: {skill_dir}")
            return ""

        # Load main file
        main_filename = SKILL_MAIN_FILE.get(skill_name, "SKILL.md")
        main_content = self._read_file(skill_dir / main_filename)
        if not main_content:
            logger.warning(f"Main skill file not found: {skill_dir / main_filename}")
            return ""

        parts = [main_content]

        # Load mode-specific support files
        for key in [(skill_name, mode), (skill_name, None)]:
            for filename in SKILL_SUPPORT_FILES.get(key, []):
                file_path = skill_dir / filename
                # Skip main file if listed as support file (daily-tracker)
                if file_path.name == main_filename:
                    continue
                content = self._read_file(file_path)
                if content:
                    parts.append(f"\n---\n\n{content}")

        result = "\n".join(parts)
        self._cache[cache_key] = result
        logger.debug(f"Loaded skill '{skill_name}' mode='{mode}' ({len(result)} chars)")
        return result

    def load_user_context(self, data_dir: Optional[Path] = None) -> str:
        """
        Load user-context.md from the data directory.

        Resolution order: explicit arg → self.data_dir (from profile) → ~/.claude/data

        Returns:
            User context content, or empty string if not found.
        """
        resolved_dir = data_dir or self.data_dir or (Path.home() / ".claude" / "data")
        path = Path(resolved_dir) / "user-context.md"

        content = self._read_file(path)
        if content:
            logger.debug(f"Loaded user-context.md ({len(content)} chars)")
            return content
        else:
            logger.warning(f"user-context.md not found at {path}")
            return ""

    def load_daily_context(self, data_dir: Optional[Path] = None) -> str:
        """
        Load daily-context.json from the data directory.

        Resolution order: explicit arg → self.data_dir (from profile) → ~/.claude/data

        Returns:
            Formatted daily context string, or empty string if not found.
        """
        resolved_dir = data_dir or self.data_dir or (Path.home() / ".claude" / "data")
        path = Path(resolved_dir) / "daily-context.json"

        if not path.exists():
            logger.warning(f"daily-context.json not found at {path}")
            return ""

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # Format key fields for the system prompt
            lines = ["## Daily Context"]
            if data.get("date"):
                lines.append(f"Date: {data['date']}")
            if data.get("location"):
                lines.append(f"Current location: {data['location']}")
            if data.get("garmin"):
                g = data["garmin"]
                if g.get("body_battery"):
                    lines.append(f"Body Battery: {g['body_battery']}")
                if g.get("sleep_score"):
                    lines.append(f"Sleep score: {g['sleep_score']}")
            if data.get("recent_people"):
                names = ", ".join(data["recent_people"][:5])
                lines.append(f"Recent people: {names}")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error loading daily-context.json: {e}")
            return ""

    def list_available_skills(self) -> list[str]:
        """List all skill names that have a valid SKILL.md or skill.md."""
        if not self.skills_dir:
            return []
        available = []
        for name, dir_name in SKILL_MAP.items():
            skill_dir = self.skills_dir / dir_name
            main_file = SKILL_MAIN_FILE.get(name, "SKILL.md")
            if (skill_dir / main_file).exists():
                available.append(name)
        return available

    # ---- Backward-compat shim used by existing prepare_llm_context ----
    def get_relevant_skills(self, mode, has_workout=False, has_meal=False) -> str:
        """Legacy method — maps old SessionMode-based loading to new skill loader."""
        from graph.state import SessionMode
        mode_str = mode.value if hasattr(mode, "value") else str(mode)
        if mode_str == SessionMode.LOGGING.value:
            return self.load_skill_content("journal", mode="logging")
        elif mode_str == SessionMode.QUERYING.value:
            return self.load_skill_content("journal", mode="querying")
        return self.load_skill_content("journal")
