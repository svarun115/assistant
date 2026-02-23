---
name: journal-gmail
description: Use transaction emails as supporting context for journal entries. Use when processing dates to corroborate activities with receipts from food delivery, rideshare, travel bookings.
---

# Gmail Workflow

Use transaction emails as **supporting context** only.

## Role of Transaction Emails

| ✅ Do | ❌ Don't |
|-------|---------|
| Corroborate activities | Flag missing receipts |
| Surface details (restaurant name, time) | Create events solely from receipts |
| Catch gaps gently | Assume all spending has email trail |

**Key principle:** User may pay via cash or other methods. Absence of email ≠ absence of activity.

## Pre-Ingestion Context Gathering

When processing a date:

```
mcp_gmail_search_emails(
  start_date: "YYYY-MM-DD",
  end_date: "YYYY-MM-DD",
  query: "receipt OR order OR booking OR confirmation"
)
```

### Common Senders

| Category | Sender patterns |
|----------|----------------|
| Food delivery | swiggy, zomato, ubereats |
| Rideshare | uber, ola, lyft |
| Travel | makemytrip, booking.com, airbnb |
| Shopping | amazon, flipkart |
| Entertainment | bookmyshow, netflix |

### Reading Full Content

Search returns metadata only. For details:
```
mcp_gmail_get_email_content(email_id: "<id>")
```

Parse for: timestamp, merchant, location, items/services.

## Integration with Journal Processing

### Step 1: Gather Context (Silent)
Before clarifying questions, fetch:
- Garmin data for the date
- Transaction emails for the date

### Step 2: Use for Clarification
If user says "ordered dinner" with no details:
> "I see a Swiggy order at 8:30pm for [restaurant]. Is this the dinner you mentioned?"

### Step 3: Corroborate, Don't Flag
If user mentions going somewhere but no Uber receipt:
- Assume other method
- Do NOT ask "Did you take Uber?"

### Step 4: Surface Gaps (Gently)
If Gmail shows unmentioned activity:
> "I noticed an Amazon order for [item]. Want to add that?"

Accept "no" gracefully.

## What NOT to Do

❌ **Create events solely from emails**
- Emails are supporting, not primary
- Always need user narrative

❌ **Flag missing transactions**
- "I don't see a receipt for the restaurant"

❌ **Store transaction amounts**
- Journal is not expense tracker
- Mention amounts only in questions

❌ **Auto-include all transactions**
- Ask before adding email-discovered activities

## Privacy Considerations

- Don't store amounts in DB
- Don't include card numbers
- Summarize ("Uber to Airport") not verbatim receipts

## Example Integration

**User says:** "Had dinner out yesterday"

**Gmail shows:**
- Zomato 7:45pm, "The Bombay Canteen"
- Uber 7:15pm to restaurant area
- Uber 10:30pm home

**Good response:**
> "I see a Zomato reservation at The Bombay Canteen at 7:45pm, and Uber trips. Is this the dinner? Any companions?"

**Bad response:**
> "I see you spent ₹2,400 at The Bombay Canteen..."

## Error Handling

| Scenario | Action |
|----------|--------|
| Gmail API unavailable | Proceed with narrative only |
| No matching emails | Normal - don't mention |
| Too many emails | Filter by relevance |
