# Locations - Complete Reference

**Complete reference for the locations system: schema, Google Places integration, and usage patterns.**

---

## 1. 🎯 Quick Reference

### What Are Locations?

The `locations` table is a **foundational reference table** that catalogs all physical places referenced throughout the database. This includes gyms, parks, restaurants, offices, universities, homes, and any other location where events or biographical milestones occur.

### Key Principle: Minimal Storage + API Fetching

**Location details (address, coordinates, etc.) are fetched from Google Places API using the `place_id`. Only user-specific metadata is stored in the database.**

This ensures:
- ✅ Data is always up-to-date (if business moves, closes, etc.)
- ✅ Minimal storage footprint
- ✅ Rich location details available on-demand
- ✅ User-specific names and notes preserved

---

## 2. �️ Available MCP Tools

### Query Tools

**✅ `search_locations` - Find Existing Locations**
```json
{
  "search_term": "Central Park",
  "location_type": "park",
  "limit": 10
}
```
**Use when:** Finding location ID before creating events. Fuzzy matching on canonical_name. Always search first to avoid duplicates!

**Returns:** Location ID, name, type, place_id

**Important:** Write tools accept only `location_id` for locations. Create or find a location first (typically via Google Places → `create_location`, or via `search_locations`), then pass the resulting `location_id` into `create_event`, `create_workout`, `create_meal`, etc.

---

## 3. 🗄️ Data Model Overview

⚠️ **Most LLM operations don't need schema details** - use the location tools documented in section 2 instead!

For advanced SQL operations, see the Database Schema Overview section in the main INSTRUCTIONS.md for complete schemas, constraints, and triggers.

### Key Location Fields

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `canonical_name` | VARCHAR(255) | Your personal name for the location (e.g., "My Gym", "Stanford") |
| `place_id` | VARCHAR(255) | Google Places ID - fetch address, coordinates, etc. from API |
| `location_type` | VARCHAR(50) | Category: gym, park, home, restaurant, office, university, etc. |
| `notes` | TEXT | Personal notes about the location |

---

## 4. 🌍 Google Places Integration

### Data Fetching Pattern

**Location details are NOT stored in the database.** Instead:
- Store only the `place_id` from Google Places API
- When displaying a location, fetch details (address, coordinates, hours, photos) from the API
- Cache API responses temporarily if needed for performance
- This ensures data is always up-to-date

**Example API fields available from `place_id`:**
- Address (formatted and components)
- Coordinates (lat/lng)
- Phone number
- Website
- Opening hours
- Photos
- Reviews/ratings

### Usage Pattern

**In application code:**
1. Query database for location with place_id
2. If place_id exists, fetch details from Google Places API
3. Display combined data: canonical_name from database + address/coordinates from API

---

## 5. 💡 Common Patterns

### Creating a Location with Google Place

When creating a location for a public venue:
1. Search Google Places API for the venue (e.g., "Gold's Gym Palo Alto")
2. Get the place_id from API response
3. Use `create_location` tool with both canonical_name and place_id
4. User can choose personal name (e.g., "My Gym") while preserving place_id for API lookups

### Creating a Location without Google Place

For private locations (home, friend's house):
- Use `create_location` with canonical_name and location_type only
- Omit place_id (will be NULL)
- No API lookup needed

### Finding Locations

Use `search_locations` tool with fuzzy matching:
- Handles typos and variations
- Searches canonical_name field
- Returns matching locations with IDs

---

## 6. 🏷️ Location Types

### Recommended location_type Values

Use consistent type values:

**Places of Activity:**
- `gym` - Fitness centers, gyms
- `park` - Parks, trails, outdoor spaces
- `restaurant` - Restaurants, cafes
- `cafe` - Coffee shops
- `office` - Offices, workspaces

**Residential:**
- `home` - Your home(s)
- `friend_home` - Friend's house
- `family_home` - Family member's house
- `apartment` - Apartment complex
- `hotel` - Hotels, temporary lodging

**Institutional:**
- `university` - Universities, colleges
- `school` - Schools
- `library` - Libraries
- `hospital` - Hospitals, clinics

**Transportation:**
- `airport` - Airports
- `station` - Train/bus stations
- `parking` - Parking locations

**Other:**
- `venue` - Event venues, concert halls
- `theater` - Movie theaters, performance venues
- `store` - Retail stores, shops
- `other` - Miscellaneous

---

## 7. 🔗 Relationships

The `locations` table is referenced by:

1. **Events** (`events.location_id`) - Where events occur
2. **Temporal Locations** (`temporal_locations.location_id`) - Geographic component of time-place periods
3. **Commutes** (`commutes.from_location_id`, `commutes.to_location_id`) - Travel origins/destinations

---

## 8. 🚨 Important Notes

### Best Practices

1. **Use Google Places When Possible**: For public places (gyms, restaurants, parks), always get the `place_id` from Google Places API
2. **Canonical Names Are Personal**: User chooses their own name (e.g., "My Gym" instead of official "Gold's Gym Palo Alto")
3. **Location Types**: Use consistent type values from recommended list
4. **NULL place_id**: Use NULL `place_id` for private locations (home, friend's house) or places not in Google
5. **Normalization**: Create one location entry, reference it many times (don't duplicate)
6. **Notes Field**: Use for personal context ("favorite window seat", "parking in back", "closes early on Sundays")

### Indexes

- `idx_locations_name` - B-tree on canonical_name (fast exact/prefix search)
- `idx_locations_name_trgm` - GIN trigram for fuzzy search (handles typos)
- `idx_locations_place_id` - B-tree on place_id (partial index, only non-NULL)
- `idx_locations_type` - B-tree on location_type (filter by category)

### Data Privacy

- **Public places**: Store place_id, fetch public details from API
- **Private places**: No place_id, store only canonical_name and notes
- **User-specific metadata**: Always stored in database (canonical_name, notes)

---

## 9. 📚 Related Resources

- **EVENTS.md** - Events reference locations via `events.location_id`
- **TRAVEL.md** - Commutes use `from_location_id` and `to_location_id`
- **PEOPLE.md** - Temporal locations link to this table for biographical history
