---
schedules:
  - name: weekly-portfolio-check
    cron: "0 14 * * 0"
    description: "Weekly portfolio check — Sunday 7:30pm IST"
    task: >
      Produce a concise weekly portfolio check-in. Pull current portfolio data
      from Google Sheets and read context from soul_md (past decisions, targets).
      1. Calculate current vs. target allocation per asset class
      2. Flag meaningful deviation (>3% drift from target)
      3. Note significant week-on-week changes in portfolio value
      4. Highlight pending decisions or action items from last session
      5. Keep to 6-8 bullet points — scannable, not exhaustive
      Do NOT make investment decisions. Just the status report.
      If nothing notable, say so briefly.
    artifact_type: portfolio_weekly

triggers:
  - id: significant_portfolio_drift
    condition: portfolio_drift_exceeds_5_percent
    message: "Portfolio drift detected — your allocation is more than 5% off target."
    priority: normal
    action: offer_foreground_session

  - id: major_market_move
    condition: market_move_exceeds_threshold
    message: "Significant market movement this week. Want to review your portfolio?"
    priority: low
    action: offer_foreground_session
---

# Financial Advisor Heartbeat

Weekly background check runs autonomously every Sunday evening.
Produces a `portfolio_weekly` artifact and notifies COS.

Proactive triggers are evaluated by COS at session start.
All triggers lead to offering a foreground session with the financial advisor —
never to making changes autonomously.
