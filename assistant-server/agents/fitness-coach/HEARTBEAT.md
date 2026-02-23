---
schedules:
  - name: weekly-training-recap
    cron: "30 2 * * 1"
    description: "Weekly training recap — Monday 8:00am IST"
    task: >
      Produce a concise weekly training recap for the completed Mon-Sun week.
      Pull the last 7 days of Garmin data (activities, daily summaries).
      Read soul_md for current goals and any noted conditions. Then:
      1. Summarize total training volume by type (running km, strength sessions, sports)
      2. Note recovery trend: avg body battery, avg sleep, resting HR vs baseline
      3. Highlight any notable achievements (distance PR, new activity, goal milestone)
      4. Flag any recovery concerns (elevated HR, low body battery, poor sleep)
      5. Give one concrete recommendation for the coming week based on the data
      Keep to 6-8 bullet points. Read-only — do NOT log workouts or modify data.
    artifact_type: fitness_weekly

triggers:
  - id: low_body_battery
    condition: body_battery_below_40_for_3_consecutive_days
    message: "Body battery has been under 40 for 3 mornings and resting HR is elevated."
    priority: normal
    action: offer_foreground_session

  - id: training_gap
    condition: no_workout_logged_for_5_days
    message: "No workout logged in 5 days."
    priority: low
    action: offer_foreground_session

  - id: new_health_condition
    condition: health_condition_logged_today
    message: "New health condition or injury logged."
    priority: high
    action: offer_foreground_session
---

# Fitness Coach Heartbeat

Weekly background recap runs every Monday morning — covers the just-completed training week.
Produces a `fitness_weekly` artifact and notifies COS.

Proactive triggers are evaluated by COS at session start.
All triggers lead to offering a foreground coaching session — never to autonomous changes.
