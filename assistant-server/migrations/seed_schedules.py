"""
Seed default scheduled agents into assistant_system.scheduler.

Run once (safe to re-run — uses INSERT ... ON CONFLICT DO NOTHING based on agent_name + user_id):

    python migrations/seed_schedules.py

Schedules seeded:
  - expenses-reminder: 1st of every month, 9:30am IST (4:00am UTC)
    Reminds user to email themselves UPI/bank PDF statements and start /expenses
  - email-triage:      daily at 9:00am IST (3:30am UTC)
  - daily-planner:     daily at 7:30am IST (2:00am UTC)
  - retro:             daily at 9:30pm IST (4:00pm UTC)
"""
import os
import json
import psycopg2
from datetime import datetime, timezone
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

USER_ID = "varun"


def compute_next_run(cron_expr: str) -> datetime:
    """Compute next run time from cron expression."""
    from croniter import croniter
    return croniter(cron_expr, datetime.utcnow()).get_next(datetime)


# ---------------------------------------------------------------------------
# Schedule definitions
# All cron expressions are in UTC.
# IST = UTC+5:30, so subtract 5h30m from desired IST time.
# ---------------------------------------------------------------------------
SCHEDULES = [
    {
        "agent_name": "expenses-reminder",
        "skill": "expenses",
        # 1st of every month at 9:30am IST = 4:00am UTC
        "cron": "0 4 1 * *",
        "config": {
            "task": (
                "Generate a brief monthly expense reminder message for the user. "
                "Tell them it is the 1st of the month and time to process last month's expenses. "
                "Give them these specific instructions:\n"
                "1. Email yourself your UPI/GPay PDF transaction statement for last month to your Gmail\n"
                "2. Also email yourself your bank statement PDF for last month\n"
                "3. Once done, start the expense review by saying '/expenses' or 'let's do expenses'\n\n"
                "Be concise. Mention the specific month being processed (last month). "
                "Do not run the actual expense workflow — just post this reminder."
            ),
            "artifact_type": "expense_reminder",
        },
    },
    {
        "agent_name": "email-triage",
        "skill": "email-triage",
        # Daily at 9:00am IST = 3:30am UTC
        "cron": "30 3 * * *",
        "config": {
            "task": (
                "Triage the inbox. Categorize recent emails, flag any that need action today, "
                "and summarize the key items. Produce a concise email digest artifact."
            ),
            "artifact_type": "email_digest",
            "max_emails": 30,
        },
    },
    {
        "agent_name": "daily-planner",
        "skill": "daily-tracker",
        # Daily at 7:30am IST = 2:00am UTC
        "cron": "0 2 * * *",
        "config": {
            "task": (
                "Generate today's daily plan. Pull today's calendar events, review recent journal "
                "context and Garmin data (sleep quality, body battery), and draft a realistic "
                "time-blocked schedule. Write the plan to the daily_plans table and produce a "
                "daily_plan artifact."
            ),
            "artifact_type": "daily_plan",
        },
    },
    {
        "agent_name": "retro",
        "skill": "retro",
        # Daily at 9:30pm IST = 4:00pm UTC
        "cron": "0 16 * * *",
        "config": {
            "task": (
                "Generate today's end-of-day retrospective. Summarize what was accomplished, "
                "compare against the daily plan, note any notable events or patterns, and "
                "produce a retro artifact. Keep it concise (5-10 bullets)."
            ),
            "artifact_type": "retro",
        },
    },
    {
        "agent_name": "fitness-coach-weekly",
        "skill": "fitness-coach",
        # Every Monday at 8:00am IST = 2:30am UTC
        # Recaps the just-completed training week (Mon-Sun) at the start of the new week
        "cron": "30 2 * * 1",
        "config": {
            "task": (
                "Produce a concise weekly training recap for the completed week. "
                "Pull the last 7 days of Garmin data (activities, daily summaries). "
                "Read the fitness context file (~/.claude/skills/fitness-coach/context.md) "
                "for current goals and any noted conditions. Then:\n"
                "1. Summarize total training volume by type (running km, strength sessions, sports)\n"
                "2. Note recovery trend: avg body battery, avg sleep, resting HR vs baseline\n"
                "3. Highlight any notable achievements (distance PR, new activity, goal milestone)\n"
                "4. Flag any recovery concerns (elevated HR, low body battery, poor sleep pattern)\n"
                "5. Give one concrete recommendation for the coming week based on the data\n"
                "6. Keep it to 6-8 bullet points — scannable, not exhaustive\n\n"
                "Do NOT log any workouts or modify any data. Read-only summary only."
            ),
            "artifact_type": "fitness_weekly",
        },
    },
    {
        "agent_name": "financial-advisor-weekly",
        "skill": "financial-advisor",
        # Every Sunday at 7:30pm IST = 2:00pm UTC
        # Good timing: markets closed for the week, user has weekend downtime to review
        "cron": "0 14 * * 0",
        "config": {
            "task": (
                "Produce a concise weekly portfolio check-in. Pull the current portfolio data "
                "from Google Sheets and read the financial context file "
                "(~/.claude/skills/financial-advisor/context.md). Then:\n"
                "1. Calculate current allocation vs. target allocation for each asset class\n"
                "2. Flag any meaningful deviation (>3% drift from target)\n"
                "3. Note any significant week-on-week changes in portfolio value\n"
                "4. Highlight any pending decisions or action items from context.md\n"
                "5. Keep the summary to 6-8 bullet points — scannable, not exhaustive\n\n"
                "Do NOT make any investment decisions or changes. Just the status report. "
                "If there is nothing notable to flag, say so briefly."
            ),
            "artifact_type": "portfolio_weekly",
        },
    },
]


inserted = 0
skipped = 0

for s in SCHEDULES:
    next_run = compute_next_run(s["cron"])
    # Use ON CONFLICT on (user_id, agent_name) — unique natural key
    cur.execute(
        """
        INSERT INTO scheduler (user_id, agent_name, skill, cron, next_run, config)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        """,
        (
            USER_ID,
            s["agent_name"],
            s["skill"],
            s["cron"],
            next_run,
            json.dumps(s["config"]),
        ),
    )
    if cur.rowcount > 0:
        print(f"  OK {s['agent_name']:25s}  cron={s['cron']:15s}  next_run={next_run.strftime('%Y-%m-%d %H:%M UTC')}")
        inserted += 1
    else:
        print(f"  - {s['agent_name']:25s}  already exists, skipped")
        skipped += 1

cur.close()
conn.close()
print(f"\nDone: {inserted} inserted, {skipped} already existed.")
