# Entity Resolution — Exercises

## Common Duplicate Traps

- "Pull Up" vs "Pull-up" (hyphenation)
- "Calve Raises" vs "Calf Raises" (spelling)
- "Lateral Lunges" vs "Lateral Lunge" (plural)
- "Kettlebell Row" vs "Row" (equipment prefix)

Search: `query(entity="exercises", where={"name": {"contains": "search_term"}})`

## Equipment is Variation, NOT Identity

**Correct:** One "Row" exercise with `equipment: ["barbell", "dumbbell", "cable", "kettlebell"]`

**Wrong:** Separate exercises for "Barbell Row", "Dumbbell Row", "Kettlebell Row"

**Exception:** Different movement patterns ARE different exercises (Incline vs Flat Bench Press).

If an equipment variant is missing, update the existing exercise first:
```
update_exercise(exercise_id, equipment=[...existing, "kettlebell"])
```
Then use that exercise ID.

## Canonical Naming

- Singular form: "Lateral Lunge" not "Lunges"
- General name: "Row" not "Kettlebell Row"
- Standard hyphenation: "Pull-up"
- No combos: "Tabata: X + Y" → log as two separate exercises

## Pre-Workout Audit (MANDATORY)

Before calling `create_workout`:
1. List EVERY exercise from the narrative
2. Resolve ALL (search + create missing)
3. Verify each ID exists and isn't soft-deleted
4. Build complete workout with all exercises
5. ONLY THEN call `create_workout`

Never: "I found 5 of 10 exercises, I'll put the rest in notes" — this is wrong.
