---
allowed_servers:
  - journal-db
  - google-workspace
---

# Financial Advisor Tool Access

- `journal-db`: log financial decisions, query past decisions and events
- `google-workspace`: read portfolio spreadsheets, expense tracking sheets, calendar

Does NOT have access to: garmin, splitwise, google-places.
(Expense tracking is handled by the expenses skill, not the financial advisor.)
