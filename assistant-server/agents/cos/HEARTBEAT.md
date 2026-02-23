---
schedules:
  - name: daily-planner
    cron: "0 2 * * *"
    description: "Daily plan — 7:30am IST from calendar + journal + Garmin"
    task: >
      Generate today's daily plan. Pull today's calendar events, review recent
      journal context and Garmin data (sleep quality, body battery), and draft
      a realistic time-blocked schedule. Write to daily_plans table and produce
      a daily_plan artifact.
    artifact_type: daily_plan

  - name: email-triage
    cron: "30 3 * * *"
    description: "Email triage — 9:00am IST daily"
    task: >
      Triage the inbox. Categorize recent emails, flag any that need action today,
      summarize key items. Produce a concise email digest artifact.
    artifact_type: email_digest

  - name: retro
    cron: "0 16 * * *"
    description: "End-of-day retro — 9:30pm IST daily"
    task: >
      Generate today's end-of-day retrospective. Summarize accomplishments,
      compare against daily plan, note notable events or patterns. Keep to
      5-10 bullets.
    artifact_type: retro

  - name: expenses-reminder
    cron: "0 4 1 * *"
    description: "Monthly expense reminder — 1st of month 9:30am IST"
    task: >
      Generate a brief monthly expense reminder message. Tell the user it is the
      1st of the month and time to process last month's expenses. Instructions:
      1. Email yourself your UPI/GPay PDF statement for last month to Gmail
      2. Also email yourself your bank statement PDF for last month
      3. Once done, start the expense review by saying '/expenses'
      Be concise. Mention the specific month being processed. Do not run the
      actual expense workflow — just post this reminder.
    artifact_type: expense_reminder

triggers:
  - id: journal_gap
    condition: no_journal_entries_for_3_days
    message: "You haven't logged anything for the past 3 days — quick catch-up?"
    priority: low
    action: offer_inline_skill
    skill: journal

  - id: upcoming_important_meeting
    condition: important_calendar_event_within_2_hours
    message: "You have {event_title} in {time} — want me to pull relevant context?"
    priority: normal
    action: offer_context_pull
---

# COS Heartbeat

COS is the always-on orchestrator. The schedules above run autonomously and
deliver artifacts + notifications. COS surfaces them at session start.

## Proactive trigger evaluation

On every session start, COS checks:
- Journal gap (no entries for 3+ days)
- Upcoming important calendar events (within 2 hours)
- Any pending notifications from other agents

COS also surfaces notifications from installed agent instances
(fitness-coach, financial-advisor) based on their own HEARTBEAT trigger declarations.
