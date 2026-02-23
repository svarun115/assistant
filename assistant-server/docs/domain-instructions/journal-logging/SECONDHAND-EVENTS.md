# Secondhand Events

Events learned about through conversation, not directly witnessed.

## When to Create

- Significant life events (accidents, health incidents, achievements)
- Events affecting family or close relationships
- Incidents that prompted action (e.g., safety improvements after a fall)

## Structure

1. **Create as generic event** with actual participant (not the user)
2. **Link to source:** Set `parent_event_id` to conversation/call where learned
3. **Tag:** `["secondhand"]` for filtering
4. **Date:** Estimate from context ("a few days ago" → ~2-3 days prior)
5. **Notes:** "Secondhand event - learned from [source] during [event]"

## Classification Rules

| Incident Type | Create As | Rationale |
|--------------|-----------|-----------|
| Mild slip/fall (no injury) | Generic event | Not health condition if no impact |
| Fall with injury | Health condition | Medical significance |
| Doctor visit | Generic event | Routine unless diagnosis |
| Hospitalization | Health condition | Medical significance |
| Achievement/milestone | Generic event | Life event |
| Travel | Generic event | Movement event |

## Example

**Amooma's Bathroom Slip:**
```json
{
  "title": "Amooma's Bathroom Slip (Secondhand)",
  "event_type": "generic",
  "start_time": "2025-09-27T12:00:00",
  "participant_ids": ["amooma-uuid"],
  "parent_event_id": "phone-call-event-uuid",
  "tags": ["secondhand", "family", "safety"],
  "description": "Secondhand: Amooma slipped in bathroom. Nothing serious. Learned from Amma during Sep 30 call. Prompted safety improvements."
}
```

## Key Rules

- Participant is the person it happened TO, not the user
- User is NOT a participant (they weren't there)
- Always link to source conversation via `parent_event_id`
- Use health_condition only for actual injuries/illness, not near-misses
