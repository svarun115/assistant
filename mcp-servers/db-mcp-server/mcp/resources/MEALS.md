# Meals - Complete Reference

**Meal tracking with food items, nutritional data, and eating context.**

---

## Quick Reference

**Tools:**
- `create_meal` - Create meals with food items and nutritional data
- SQL via `execute_sql_query` - Query recent meals, nutrition analysis, eating patterns

**Meal Types:** breakfast, lunch, dinner, snack, brunch, dessert

**Meal Sources:** home_cooked, restaurant, takeout, meal_prep, fast_food, buffet

---

## SQL Query Patterns for Meals

**All meal queries use `execute_sql_query()`**

### Get Recent Meals
```sql
SELECT 
    m.id, m.meal_title, e.start_time::date as meal_date,
    m.meal_type, m.portion_size, m.cuisine,
    l.canonical_name as location,
    STRING_AGG(DISTINCT p.canonical_name, ', ') as participants,
    SUM(fi.calories) as total_calories,
    SUM(fi.protein_g) as total_protein,
    SUM(fi.carbs_g) as total_carbs,
    SUM(fi.fats_g) as total_fats
FROM meals m
JOIN events e ON m.event_id = e.id
LEFT JOIN locations l ON e.location_id = l.id
LEFT JOIN event_participants ep ON e.id = ep.event_id
LEFT JOIN people p ON ep.person_id = p.id
LEFT JOIN meal_items fi ON m.id = fi.meal_id
WHERE e.start_time >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY m.id, e.id, l.canonical_name, m.meal_title, m.meal_type, m.portion_size, m.cuisine
ORDER BY e.start_time DESC
LIMIT 20;
```

### Get Meals by Date Range
```sql
SELECT 
    e.start_time::date as meal_date,
    m.meal_title,
    m.meal_type,
    SUM(fi.calories) as total_calories,
    SUM(fi.protein_g) as total_protein,
    l.canonical_name as location
FROM meals m
JOIN events e ON m.event_id = e.id
LEFT JOIN locations l ON e.location_id = l.id
LEFT JOIN meal_items fi ON m.id = fi.meal_id
WHERE e.start_time >= '2025-10-01'
  AND e.start_time < '2025-11-01'
GROUP BY e.id, e.start_time, m.id, m.meal_title, m.meal_type, l.canonical_name
ORDER BY e.start_time DESC;
```

### Filter by Meal Type
```sql
SELECT 
    e.start_time::date as meal_date,
    m.meal_title, m.meal_type, m.cuisine,
    SUM(fi.calories) as total_calories,
    COUNT(fi.id) as food_items
FROM meals m
JOIN events e ON m.event_id = e.id
LEFT JOIN meal_items fi ON m.id = fi.meal_id
WHERE m.meal_title = 'breakfast'
  AND e.start_time >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY m.id, e.id, m.meal_title, m.meal_type, m.cuisine
ORDER BY e.start_time DESC;
```

---

### Write Tool: `create_meal`
**Create meals with food items and automatic nutritional calculations**

**When to use:**
- Creating meals from journal entries
- Recording eating experiences with detailed food items
- Tracking nutritional intake

**Parameters:**
```json
{
  "event": {
    "title": "Post-workout Lunch",                        // Required
    "description": "High-protein recovery meal",          // Optional
    "start_time": "2025-10-12T12:30:00",                 // Required (ISO 8601)
    "end_time": "2025-10-12T13:00:00",                   // Optional
    "category": "social",                                 // Optional
    
    // Location
    "location_id": "uuid-from-search",                   // Use search_locations/create_location first
    
    "participant_names": ["Sarah"],                       // Auto-creates if needed
    // OR
    "participant_ids": ["uuid-1"],                       // Validates exist
    
    "tags": ["nutrition", "post-workout"]                 // Optional
  },
  "meal": {
    "meal_name": "Recovery Lunch",                        // Optional
    "meal_title": "lunch",                                // Required: "breakfast", "lunch", "dinner", "snack", "brunch", "dessert"
    "meal_type": "home_cooked",                          // Optional: "home_cooked", "restaurant", "takeout", etc.
    "portion_size": "medium",                            // Optional: "small", "medium", "large", "extra_large"
    "context": "post_workout",                           // Optional: "pre_workout", "post_workout", "celebration", etc.
    
    "items": [                                           // Optional (but recommended)
      {
        "item_name": "Grilled chicken breast",           // Required
        "quantity": "200g",                              // Optional
        "calories": 330,                                 // Optional
        "protein_g": 62,                                // Optional
        "carbs_g": 0,                                   // Optional
        "fats_g": 7,                                    // Optional
        "fiber_g": 0                                    // Optional
      },
      {
        "item_name": "Brown rice",
        "quantity": "1 cup",
        "calories": 215,
        "carbs_g": 45,
        "protein_g": 5,
        "fats_g": 2,
        "fiber_g": 3.5
      }
    ],
    
    "preparation_method": "Grilled chicken, steamed vegetables",  // Optional
    "cuisine": "American"                                         // Optional
  }
}
```

**Dependency Chain:**
1. **Location**: Use `location_id` (create/search locations first)
2. **People**: Auto-created via `participant_names` OR validated via `participant_ids`
3. **Event**: Created with resolved references
4. **Meal**: Created with event_id and items
5. **Nutritional Totals**: Automatically calculated from items

**Automatic Calculations:**
- `total_calories` = sum of all item calories
- `total_protein_g` = sum of all item protein
- `total_carbs_g` = sum of all item carbs
- `total_fats_g` = sum of all item fats

**Usage Patterns:**

**Pattern 1: Simple Meal (No Nutritional Data)**
```json
{
  "event": {
    "title": "Dinner with friends",
    "start_time": "2025-10-12T19:00:00",
    "location_id": "<location-uuid>",
    "participant_names": ["Alice", "Bob"]
  },
  "meal": {
    "meal_title": "dinner",
    "meal_type": "restaurant",
    "cuisine": "Italian",
    "items": [
      {"item_name": "Fettuccine Alfredo"},
      {"item_name": "Caesar Salad"},
      {"item_name": "Garlic Bread"}
    ]
  }
}
```

**Pattern 2: Detailed Meal (With Nutrition)**
```json
{
  "event": {
    "title": "Post-workout meal",
    "start_time": "2025-10-12T13:00:00",
    "location_id": "<location-uuid>"
  },
  "meal": {
    "meal_title": "lunch",
    "meal_type": "home_cooked",
    "portion_size": "large",
    "context": "post_workout",
    "items": [
      {
        "item_name": "Grilled chicken",
        "quantity": "200g",
        "calories": 330,
        "protein_g": 62,
        "carbs_g": 0,
        "fats_g": 7
      },
      {
        "item_name": "Sweet potato",
        "quantity": "1 medium",
        "calories": 112,
        "protein_g": 2,
        "carbs_g": 26,
        "fats_g": 0
      }
    ]
  }
}
```

**Best Practices:**
- ✅ Use `location_id` from `search_locations`/`create_location`
- ✅ Use `participant_ids`/`location_id` when you have UUIDs from searches
- ✅ Provide nutritional data when available (enables analytics)
- ✅ Provide timestamps in ISO 8601 format
- ⚠️ Nutritional totals are automatically calculated - don't provide them manually
- ⚠️ Items array is optional but recommended for detailed tracking

**Error Handling:**
- Invalid UUID format → Error with correct format
- Missing location/person ID → Error message suggesting entity doesn't exist
- Invalid timestamp → Error message with ISO 8601 format requirement

---

## Tool Usage

**Typical workflows:**
- "What did I eat recently?" → Use SQL queries (Get Recent Meals section above)
- "What did I eat on [date]?" → Use SQL with date filter
- "Show meals with [person]" → Use SQL with JOIN to event_participants

**SQL-First Philosophy:** Use `execute_sql_query()` with the patterns above for all data retrieval.

---

## Journal Extraction

### Extraction Pattern

When extracting meal information from journal entries, identify:

1. **Event details (WHO, WHERE, WHEN)**
   - Start time
   - Location (restaurant name or "Home")
   - Participants (dining companions)
   - Event title and description

2. **Meal specifics (WHAT)**
   - Meal title (breakfast, lunch, dinner, snack)
   - Meal type (home_cooked, restaurant, takeout)
   - Portion size (small, medium, large)
   - Food items (with optional nutritional data)

3. **Tool to use**: `create_meal` with event-first architecture

### Example Extractions

**Simple breakfast:**
```
Journal: "Had scrambled eggs for breakfast at 8am"

Event:
  event_type = 'meal'
  start_time = 08:00:00
  title = "Scrambled eggs and toast"
  location_id = "<location-uuid>" (resolve/create first)

Meal:
  meal_title = 'breakfast'
  meal_type = 'home_cooked' (inferred)
  portion_size = 'regular' (inferred)
```

**Dinner with friends:**
```
Journal: "Had dinner at Olive Garden with Sarah and Mike at 7pm. Pizza was amazing!"

Event:
  event_type = 'meal'
  start_time = 19:00:00
  title = "Pizza at Olive Garden"
  notes = "Pizza was amazing!"
  location_id = "<location-uuid>"
  tags = ['social']

Meal:
  meal_title = 'dinner'
  meal_type = 'restaurant'
  portion_size = 'regular'

Participants: Sarah, Mike (role='friend')
```

**Post-workout snack:**
```
Journal: "Quick protein shake after gym at 11:30am"

Event:
  event_type = 'meal'
  start_time = 11:30:00
  title = "Protein shake"
  tags = ['post_workout']
  location_id = "<location-uuid>"

Meal:
  meal_title = 'snack'
  meal_type = 'home_cooked'
  portion_size = 'light'
```

### Inference Guidelines

**Meal title from timing:** 5-10am→breakfast, 11am-2pm→lunch, 5-9pm→dinner, other→snack

**Meal type from context:** "cooked"→home_cooked, restaurant name→restaurant, "delivery"→delivered, "takeout"→takeout

**Portion size:** "light/small"→light, "big/large"→heavy, default→medium

---

## Important Notes

- Event with `event_type='meal'` MUST have meals entry (enforced by trigger)
- Store descriptive title in event.title ("Scrambled eggs and toast")
- Store taste/feelings in event.notes
- Use tags for context (`post_workout`, `celebration`, `healthy`)
- Don't store detailed nutrition data (use external apps)

---

## Related Resources

- **EVENTS.md** - Event system architecture
- **PEOPLE.md** - Tracking dining companions
- **LOCATIONS.md** - Restaurant reference
