# Common Pitfalls

Edge cases and rules to avoid data quality issues.

## Time & Date

### Midnight Is Not a Hard Cut
- Treat 00:00–02:00 events as possible spillover if user hasn't slept
- Ask if unclear which day an event belongs to

### Meal End-Time Inference
- Infer end time only if next event starts within 1 hour
- Otherwise ask

### No Invention
- If times are relative ("this morning"), keep unspecified unless clear anchor
- Never fabricate timestamps

## Entertainment

### Completion vs Event Timing
- `completion_status` = whether *media itself* was finished
- NOT whether event has `end_time`
- Theatre movie = mark as `finished` (you watched it all)
- Timestamps and completion are independent

## Sleep

### Segmentation
- If user reports waking and returning to sleep: create separate segments
- Update first sleep's end_time to wake time
- Create second sleep event for return-to-sleep
- "Awake in bed" (cuddling, scrolling) = separate generic event, not sleep

## Workouts

### Structure Rules
- Pure cardio (run/bike/swim): no exercises array
- Strength/gym: structured exercises/sets
- Duration-based sets: leave reps null (not reps=0)

### Exercise/Rehab Blocks
- Any deliberate exercise = workout, not generic event
- Gym, rehab exercises, stretching, yoga, band work → use `create_workout`
- If doesn't fit workout_subtype enum, omit it and use notes

## Specialization Updates

### Fields May Not Update via Event Updates
If changing specialization-only field (e.g., `entertainment.completion_status`):
1. Snapshot old event details
2. Ensure no critical external links (Garmin IDs)
3. Soft-delete old event
4. Recreate with correct specialization
5. Verify via SQL
6. Keep deleted record (audit trail)

## Health Conditions

### Classification
**DO use health_condition for:**
- Actual injuries requiring treatment
- Illnesses with symptoms/duration
- Conditions requiring medication/doctor

**Do NOT use health_condition for:**
- Minor incidents with no lasting impact
- Near-misses or close calls
- Precautionary measures

Example: Slip with no injury → generic event. Fall causing sprain → health_condition.

## Source Conflicts

- Show both values
- Ask which to trust
- Prefer Garmin for linked workout stats

## Schema-First Writes

- Never write fields not in SQL schema
- Tool signatures may be broader than DB supports
- Verify schema before writing unusual fields
