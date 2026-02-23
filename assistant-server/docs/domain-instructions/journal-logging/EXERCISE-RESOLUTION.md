# Exercise Resolution Procedure

> ⚠️ **MANDATORY before creating workout exercises**

## Common Mistakes That Cause Duplicates

- Creating "Pull Up" when "Pull-up" exists (formatting/hyphenation)
- Creating "Calve Raises" when "Calf Raises" exists (spelling variants)
- Creating "Lateral Lunges" when "Lateral Lunge" exists (singular/plural)
- Creating "Kettlebell Row" when "Row" exists with kettlebell in equipment array
- Creating combo exercises like "Tabata: Leg Tuckins + Hollow Hold" instead of logging separately

## Resolution Steps

### 1. Build Search Terms

For each exercise mentioned, generate variants:
- Singular/plural: "lunge" / "lunges"
- Hyphenation: "pull-up" / "pull up" / "pullup"
- Common misspellings: "calf" / "calve"
- Equipment prefix removal: "KB Row" → search for "Row"
- Abbreviated forms: "KB" = "Kettlebell", "DB" = "Dumbbell"

### 2. Search Exercises Broadly

```sql
SELECT id, canonical_name, category, primary_muscle_group, equipment, variants
FROM exercises
WHERE COALESCE(is_deleted, false) = false
  AND (
    canonical_name ILIKE '%lunge%'
    OR canonical_name ILIKE '%lateral%'
    OR '%lunge%' = ANY(variants)
  )
ORDER BY canonical_name;
```

### 3. Equipment Is a Variation, NOT a Separate Exercise

**Core principle:**
- ✅ One "Row" exercise with equipment: `["barbell", "dumbbell", "cable", "kettlebell"]`
- ❌ Separate exercises: "Barbell Row", "Dumbbell Row", "Kettlebell Row"

- ✅ One "Calf Raise" exercise with equipment: `["machine", "dumbbell", "bodyweight"]`
- ❌ Separate exercises: "Machine Calf Raise", "Standing Calf Raise"

**Exception:** If movement pattern is fundamentally different (e.g., "Incline Bench Press" vs "Flat Bench Press" — different angle = different muscle recruitment), it's a distinct exercise.

### 4. If Match Exists

Use existing exercise ID. If equipment variant isn't in array, update first:
```
mcp_personal_jour_update_exercise(exercise_id, equipment=[...existing, "new_equipment"])
```

### 5. If No Match Exists

Create with canonical naming:
- Most general name (no equipment prefix): "Row" not "Kettlebell Row"
- Include all equipment variants in equipment array
- Singular form preferred: "Lateral Lunge" not "Lateral Lunges"
- Standard hyphenation: "Pull-up" (hyphenated)

### 6. Never Create Combo Exercises

Log each exercise separately:
- ❌ "Tabata: Leg Tuckins + Hollow Hold"
- ✅ Two exercises: "Leg Tuck-in" (set 1) and "Hollow Hold" (set 2)

## Example Resolution Workflow

User says: "Did KB rows, seated calf raises, and weighted dead bugs"

1. **Search "row":**
   - Found: "Row" (id: abc123, equipment: ["barbell", "dumbbell", "cable"])
   - → Use abc123, but first update equipment to add "kettlebell"

2. **Search "calf":**
   - Found: "Calf Raise Machine" (id: def456)
   - Found: "Standing Calf Raise" (id: ghi789)
   - → "Seated" is machine-based, use def456

3. **Search "dead bug":**
   - Found: "Deadbugs" (id: jkl012, equipment: ["bodyweight", "dumbbell"])
   - → Use jkl012, "weighted" = dumbbell variation (already in equipment)

## Pre-Workout Audit

Before calling `create_workout`, verify:
- Each exercise ID exists and is not soft-deleted
- No two IDs point to same real-world exercise
- Equipment variants captured in array, not as separate exercises
