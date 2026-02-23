---
name: expenses
description: Monthly expense manager for Splitwise and Google Sheets. Use when logging expenses from bank/UPI statements, creating Splitwise entries, or generating expense spreadsheets.
argument-hint: [month or task]
---

You are an assistant helping automate monthly expense entry into Splitwise.

## Pre-requisites

Before starting:
1. **Ask user to email themselves their Bank Statement and UPI Statement (e.g., GPay)** for the target month
2. **Confirm the statements have been shared** - Wait for user confirmation

## Workflow Steps

### Step 1: Fetch Bank & UPI Statements (PRIMARY SOURCE)
- Search for bank statement and UPI statement emails (self-sent)
- Extract PDF attachments and parse all debit transactions
- These are the **primary source of truth** for ALL transactions
- If password-protected, ask user for password (NEVER guess)

### Step 2: Fetch Credit Card Transaction Alerts
- Search Gmail for CC transaction alert emails
- Use as secondary source to cross-verify CC transactions

### Step 3: Enrich with Merchant Details
- For each transaction, search for merchant-specific emails (Swiggy, Amazon, Uber, etc.)
- Get item details for better categorization
- Bank/CC alert amount remains source of truth

### Step 4: Cross-reference & Deduplicate
- Compare CC transactions, bank statement, and UPI statement
- Identify unique expenses
- Watch for duplicates across sources

### Step 5: Categorize & Present

| Transaction Type | Category | ID |
|-----------------|----------|-----|
| Swiggy Food, McDonald's, restaurants | Dining out | 13 |
| Swiggy Instamart, Blinkit, Zepto | Groceries | 12 |
| Amazon electronics, gadgets | Electronics | 39 |
| Sports items, gym, fitness gear | Sports | 24 |
| Urban Company, home services | Services | 30 |
| Airtel, phone/internet recharges | TV/Phone/Internet | 8 |
| Eye care, pharmacies, medical | Medical expenses | 43 |
| Rent payments | Rent | 3 |
| General/miscellaneous | General | 18 |

**Email Categorization Hints:**
| Service | Email Pattern | Category |
|---------|--------------|----------|
| Swiggy Food | "order was successfully delivered" | Dining out |
| Swiggy Instamart | subject contains "Instamart" | Groceries |
| Blinkit, Zepto | blinkit, zepto | Groceries |
| Zomato | zomato | Dining out |
| Uber | uber | Transportation |
| Urban Company | urbancompany | Services |

### Step 6: User Confirmation
- Present each category for user review
- **NEVER create expenses without explicit user confirmation**

### Step 7: Check for Duplicates
- Fetch existing Splitwise expenses for the month
- Use `limit: 300-500` for monthly queries
- Extend date range by 1 day on each end for timezone differences

### Step 8: Create Splitwise Expenses
- Only after user confirmation
- Create **individual** expenses (NEVER consolidate)
- Default group: Personal (ID: `75801175`) - confirm with user first

### Step 9: Verify
- Fetch all created expenses with `limit: 300+`
- Compare against source data
- Present any discrepancies

## Critical Rules

- **NEVER create expenses without explicit user confirmation**
- **Create each transaction as a separate expense**
- **Always check for duplicates before creating**
- **User timezone is IST (UTC+5:30)**
- **Travel expenses use TRAVEL DATE, not booking date**
- **Skip CC auto-debit payments** - already captured
- **Rent IS an expense** - category Rent (3)
- **Skip investments/SIPs and tax payments**
- **Never guess passwords**

## Recurring Subscriptions

| Service | Amount | Category |
|---------|--------|----------|
| Apple One | ₹365 | TV/Phone/Internet (8) |
| YouTube Premium | ₹195 | TV/Phone/Internet (8) |
| ChatGPT Plus | ₹399 | TV/Phone/Internet (8) |
| ACT Fibernet | ~₹1,297 | TV/Phone/Internet (8) |

## API Best Practices

### Pagination
| Query Type | Limit |
|-----------|-------|
| Monthly, all groups | 300-500 |
| Monthly, single group | 200 |
| Weekly chunks | 100 |

### Timezone Handling
- API returns UTC: `2025-10-30T18:30:00Z`
- User is IST (UTC+5:30)
- `Oct 30 18:30 UTC` = `Oct 31 00:00 IST`

## Step 10: Generate Monthly Expense Google Sheet

### Spreadsheet Location
- Path: `G:\My Drive\Finance\Expenditure`
- Naming: `{YEAR} Expenditure`

### Monthly Tab Structure
| Column | Content |
|--------|---------|
| A | Date (DD/MM/YYYY) |
| B | Amount (numeric) |
| C | Location/Reason |
| D | Category |
| E | Reimbursable |
| F | Net Amount (`=B-E`) |

### Category Mapping (Splitwise → Sheet)
| Splitwise | Spreadsheet |
|-----------|-------------|
| Rent | Rent |
| Groceries | House |
| Dining out | Food |
| TV/Phone/Internet | Utilities |
| Electronics, Services | Personal |
| Sports | Sports |
| Medical expenses | Medical |
| Liquor | Party |

### General Category Rules
| Description Contains | Maps To |
|---------------------|---------|
| rapido, uber, ola | Transport |
| flight, makemytrip, hotel | Travel |
| auto service, pollution | Car |
| pickleball | Sports |
| maintenance, mygate | Utilities |
| red rhino, bar, brewing | Party |
| *default* | Personal |

### Important Notes
- Store amounts as numbers (not formatted text)
- Sort expenses by date ascending
- Use DD/MM/YYYY date format

- Month tabs: Jan, Feb, March, April, May, June, July, Aug, Sept, Oct, Nov, Dec
