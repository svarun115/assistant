# People - Complete Reference

**Complete reference for people management: schema, biographical tracking, relationships, timeline history, and extraction guide.**

---

## 1. 🎯 Quick Reference

### What Is the People System?

The people system captures biographical information about everyone in your life. It follows a **person-centric architecture** with structured notes, family relationships, and timeline tracking (where they lived, worked, studied).

### Core Tables

| Table | Purpose | Key Feature |
|-------|---------|-------------|
| `people` | Core identity and classification | Canonical name, aliases, relationship type |
| `person_notes` | Structured biographical notes | Categorized, tagged, sourced |
| `person_relationships` | Family tree | Automatic reciprocal relationships |
| `temporal_locations` | Time + place periods | Person-agnostic, enables data reuse |
| `person_residences` | Where they lived | Links people to temporal locations |
| `person_work` | Employment history | Company, role, timeline |
| `person_education` | Educational history | Institution, degree, field |

### Architecture Principle

```
people (core identity)
  ├── person_notes (structured biographical notes)
  ├── person_relationships (family tree)
  ├── temporal_locations (base: time + place)
  │   ├── person_residences (where they lived)
  │   ├── person_work (where they worked)
  │   └── person_education (where they studied)
```

---

## 2. � Key Concepts

```sql
CREATE TABLE people (
    id UUID PRIMARY KEY,
    
    -- Core Identity
    canonical_name VARCHAR(255) NOT NULL,
    aliases TEXT[],  -- Nicknames, alternate names
    
    -- Relationship Classification
    relationship person_relationship_enum,  -- friend, family, colleague, partner, acquaintance, mentor, other
    category person_category_enum,          -- close_friend, friend, acquaintance, family, work, not_met, other
    
    -- Biographical Information
    birthday DATE,
    ethnicity VARCHAR(100),
    origin_location VARCHAR(255),
    known_since INTEGER,            -- Year first met
    last_interaction_date DATE,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Person Notes (Structured Biography)

```sql
CREATE TABLE person_notes (
    id UUID PRIMARY KEY,
    person_id UUID REFERENCES people(id) ON DELETE CASCADE,
    
    note_date DATE,
    note_type person_note_type,        -- HOW information is characterized
    category person_note_category,     -- WHAT domain it belongs to
    text TEXT NOT NULL,
    source VARCHAR(100),               -- How info was obtained
    context TEXT,
    tags TEXT[],
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Person Relationships (Family Tree)

```sql
CREATE TABLE person_relationships (
    id UUID PRIMARY KEY,
    person_id UUID REFERENCES people(id) ON DELETE CASCADE,
    related_person_id UUID REFERENCES people(id) ON DELETE CASCADE,
    relationship_type family_relationship_type NOT NULL,
    notes TEXT,
    
    UNIQUE(person_id, related_person_id, relationship_type),
    CHECK (person_id != related_person_id)
);
```

### Temporal Locations (Time + Place Base)

```sql
CREATE TABLE temporal_locations (
    id UUID PRIMARY KEY,
    
    location_id UUID NOT NULL REFERENCES locations(id),
    
    start_date VARCHAR(10),  -- Partial ISO-8601: YYYY, YYYY-MM, or YYYY-MM-DD
    end_date VARCHAR(10),    -- Partial ISO-8601: YYYY, YYYY-MM, or YYYY-MM-DD
    is_current BOOLEAN DEFAULT FALSE,
    
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    
    CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)
);
```

### Person Residences, Work, Education

```sql
CREATE TABLE person_residences (
    id UUID PRIMARY KEY,
    person_id UUID REFERENCES people(id) ON DELETE CASCADE,
    temporal_location_id UUID REFERENCES temporal_locations(id) ON DELETE CASCADE,
    notes TEXT
);

CREATE TABLE person_work (
    id UUID PRIMARY KEY,
    person_id UUID REFERENCES people(id) ON DELETE CASCADE,
    temporal_location_id UUID REFERENCES temporal_locations(id) ON DELETE CASCADE,
    company VARCHAR(255) NOT NULL,
    role VARCHAR(255) NOT NULL,
    notes TEXT
);

CREATE TABLE person_education (
    id UUID PRIMARY KEY,
    person_id UUID REFERENCES people(id) ON DELETE CASCADE,
    temporal_location_id UUID REFERENCES temporal_locations(id) ON DELETE CASCADE,
    institution VARCHAR(255) NOT NULL,
    degree VARCHAR(100) NOT NULL,
    field VARCHAR(255),
    notes TEXT
);
```

---

## 3. 🔑 Key Concepts

### canonical_name vs aliases

- **canonical_name**: Primary name you use (required) - e.g., "Ishar Menon"
- **aliases**: Array of nicknames, alternate spellings - e.g., ["Ishu", "Ish"]

### relationship vs category

**These serve DIFFERENT purposes:**
- **relationship**: TYPE of relationship (friend, family, colleague)
- **category**: How CLOSE you are / organizational bucket

**Examples:**
- Close personal friend: relationship='friend', category='close_friend'
- Work colleague you're friendly with: relationship='colleague', category='friend'
- Family member: relationship='family', category='family'
- Online friend not met in person: relationship='friend', category='not_met'

### known_since vs last_interaction_date

- **known_since**: Year you first met (integer like 2022)
- **last_interaction_date**: Most recent interaction (full date)

### Note Types vs Categories

**note_type** - HOW the information is characterized:
- `biographical` - Basic life facts
- `health` - Medical/health information
- `preference` - Likes/dislikes
- `interest` - Hobbies, passions
- `story` - Anecdotes, memorable events
- `personality` - Character traits
- `achievement` - Accomplishments
- `other` - Other types

**category** - WHAT domain the information belongs to:
- `health`, `personality`, `hobbies`, `family`, `career`, `preferences`, `beliefs`, `achievements`, `stories`, `other`

---

## 4. 🌳 Family Relationships (Auto-Reciprocal)

### CRITICAL: Automatic Reciprocal Relationships

**The database AUTOMATICALLY creates the reverse relationship!**

**Asymmetric (different each way):**
- Alice → Bob as 'parent' automatically creates Bob → Alice as 'child'
- Mappings: `parent` ↔ `child`, `grandparent` ↔ `grandchild`, `aunt_uncle` ↔ `niece_nephew`

**Symmetric (same both ways):**
- Bob → Charlie as 'sibling' automatically creates Charlie → Bob as 'sibling'
- Mappings: `spouse` ↔ `spouse`, `sibling` ↔ `sibling`, `cousin` ↔ `cousin`

### Best Practice: Only Create ONE Direction

**✅ DO THIS:**
Use the `add_person_relationship` tool with `bidirectional: true` to automatically create both directions.

**❌ DON'T DO THIS:**
Don't manually create both directions - the system handles reciprocals automatically.

---

## 5. ⏰ Temporal Locations (Data Reuse Pattern)

### Key Insight: Person-Agnostic Base Table

`temporal_locations` represents time periods at specific locations **independent of people**. This enables data reuse - multiple people can reference the same temporal location entry.

**Benefits:**
1. **Data Reuse**: Roommates, colleagues, classmates share ONE temporal location
2. **Normalization**: Store time-place data once
3. **Queryability**: Easy to find all people at a location during a time period

### Example: Roommates

When Alice and Bob are roommates 2020-2022:
- ONE temporal location is created for the apartment + time period
- BOTH Alice and Bob link to the same temporal location via `person_residences`
- Result: Data reuse - 1 temporal_locations entry, 2 person_residences entries

### Example: Colleagues

When Alice (Engineer) and Bob (PM) both work at Google 2020-present:
- ONE temporal location is created for Google campus + time period
- BOTH link to it via `person_work` with their respective roles
- Result: Shared workplace context with individual role tracking

### Date Format

Dates are stored as partial ISO-8601 strings for flexibility:
- **Year only:** `2020` (YYYY)
- **Year and month:** `2020-06` (YYYY-MM)
- **Full date:** `2020-06-15` (YYYY-MM-DD)

---

## 6. 📝 Journal Extraction Guide

### Creating a Complete Person Profile

When extracting person information from journal entries, use the following MCP tools in sequence:

1. **Search for existing person** - Use `search_people` to avoid duplicates
2. **Create person** - Use `create_person` with core identity information
3. **Add relationships** - Use `add_person_relationship` for family/social connections
4. **Add biographical notes** - Use `add_person_note` for health, interests, stories, etc.
5. **Add work history** - Use `add_person_work` for employment timeline
6. **Add education** - Use `add_person_education` for academic history
7. **Add residences** - Use `add_person_residence` for where they lived

See section 8 below for complete tool documentation and workflow examples.

---

## 7. 🚨 Important Notes

### Best Practices

1. **Check for Existing Temporal Locations**: Before creating new, search for existing (roommates, colleagues, classmates)
2. **Use Appropriate Date Precision**: Be honest about what you know (year/month/day)
3. **Prefer Location References**: Use `location_id` when location exists in catalog
4. **Consistent Naming**: Use canonical names consistently for companies, institutions
5. **Tag Person Notes Effectively**: Use lowercase, be specific, include time references
6. **Create Only ONE Relationship Direction**: Let triggers handle reciprocals
7. **Update Last Interaction Date**: Keep track of recent interactions

### Integration with Events

People connect to events via event_participants. When creating events (workouts, meals, etc.), use the hybrid resolution pattern:
- **participant_names**: Auto-creates people if they don't exist
- **participant_ids**: Uses existing people (validates existence)

To find all events with a specific person, use SQL:
```sql
SELECT e.* FROM events e
JOIN event_participants ep ON e.id = ep.event_id
JOIN people p ON ep.person_id = p.id
WHERE p.canonical_name ILIKE '%Name%' OR 'Name' = ANY(p.aliases)
ORDER BY e.start_time DESC;
```

### Person Notes - source Field Values

- `conversation` - Told directly in conversation
- `observation` - You observed it yourself
- `social_media` - From Facebook, LinkedIn, Instagram
- `told_by_others` - Someone else told you
- `inference` - You inferred/deduced it
- `document` - From resume, bio, profile
- `other` - Other source

---

## 8. 🛠️ Available MCP Tools

### Query Tools (Read Operations)

**✅ `search_people` - Find Existing People**
```json
{
  "search_term": "Gauri",
  "relationship": "family",
  "limit": 10
}
```
**Use when:** Finding person ID before adding notes or relationships. Fuzzy matching on canonical_name and aliases. Always search first to avoid duplicates!

**✅ `get_person_details` - Get Complete Person Profile**
```json
{
  "person_id": "62159a85-7443-4bce-a23d-b18a7cd5ce9f"
}
```
**Returns:** Complete person info including notes, relationships, work history, education, residences

---

### Write Tools - Core People Management

**✅ `create_person` - Create Person with Full Biographical Details**
```json
{
  "canonical_name": "Gauri",
  "aliases": ["G"],
  "relationship": "family",
  "category": "family",
  "birthday": "1993-09-26",
  "ethnicity": "Indian",
  "origin_location": "Bangalore",
  "known_since": 2017,
  "last_interaction_date": "2025-10-14"
}
```
**Use when:** Manually creating a person with comprehensive information (not just auto-created via events)

**✅ `add_person_note` - Add Biographical Note/Observation**
```json
{
  "person_id": "62159a85-7443-4bce-a23d-b18a7cd5ce9f",
  "text": "Had thyroid ultrasound and biopsy scheduled",
  "note_type": "health",
  "category": "health",
  "note_date": "2025-08-01",
  "source": "conversation",
  "tags": ["thyroid", "medical", "health"]
}
```
**Use when:** Recording biographical information, health events, personality traits, interests, stories, achievements

**✅ `add_person_relationship` - Define Family/Social Connections**
```json
{
  "person_id": "user-id",
  "related_person_id": "gauri-id",
  "relationship_type": "spouse",
  "notes": "Married in 2018",
  "bidirectional": true
}
```
**Use when:** Defining family trees, social connections. Set `bidirectional: true` to auto-create reverse relationship.

---

### Write Tools - Timeline & History Management

**✅ `update_person` - Update Existing Person Fields**
```json
{
  "person_id": "uuid-123",
  "category": "close_friend",
  "last_interaction_date": "2025-10-14"
}
```
**Use when:** Modifying biographical information, changing classifications. Only updates provided fields, leaves others unchanged.

**✅ `add_person_work` - Add Work History**
```json
{
  "person_id": "uuid-123",
  "company": "Microsoft",
  "role": "Senior Engineer",
  "location_id": "microsoft-campus-id",
  "start_date": "2020-01-01",
  "is_current": true
}
```
**Use when:** Recording employment history. Creates temporal_location for data reuse with colleagues.

**✅ `add_person_education` - Add Education History**
```json
{
  "person_id": "uuid-123",
  "institution": "Stanford University",
  "degree": "BS",
  "field": "Computer Science",
  "start_date": "2012-09-01",
  "end_date": "2016-06-01"
}
```
**Use when:** Recording educational background. Creates temporal_location for data reuse with classmates.

**✅ `add_person_residence` - Add Residence History**
```json
{
  "person_id": "uuid-123",
  "location_id": "uuid-location-456",
  "start_date": "2022-01-01",
  "is_current": true
}
```
**Use when:** Recording where someone lived (requires location_id from locations table). Creates temporal_location for data reuse with roommates.

### Workflow: Import Person with Complete Profile

**Step 1: Search for existing person (avoid duplicates)**
```json
// Use: search_people
{"search_term": "Gauri"}
```

**Step 2: Create person if not found**
```json
// Use: create_person
{
  "canonical_name": "Gauri",
  "aliases": ["G"],
  "relationship": "family",
  "category": "family",
  "birthday": "1993-09-26",
  "known_since": 2017
}
// Returns: {"person_id": "uuid-123"}
```

**Step 3: Add biographical notes**
```json
// Use: add_person_note (multiple times for different notes)
{
  "person_id": "uuid-123",
  "text": "Software engineer at Microsoft",
  "note_type": "biographical",
  "category": "career",
  "tags": ["microsoft", "engineer", "career"]
}
```

**Step 4: Define relationships**
```json
// Use: add_person_relationship
{
  "person_id": "my-id",
  "related_person_id": "uuid-123",
  "relationship_type": "spouse",
  "bidirectional": true
}
// Creates: You → Gauri: spouse AND Gauri → You: spouse
```

**Step 5: Add work history**
```json
// Use: add_person_work
{
  "person_id": "uuid-123",
  "company": "Microsoft",
  "role": "Software Engineer",
  "start_date": "2020-01-01",
  "is_current": true
}
```

**Step 6: Add education history**
```json
// Use: add_person_education
{
  "person_id": "uuid-123",
  "institution": "Stanford University",
  "degree": "BS",
  "field": "Computer Science",
  "start_date": "2012-09-01",
  "end_date": "2016-06-01"
}
```

**Step 7: Add residence history**
```json
// Use: add_person_residence
{
  "person_id": "uuid-123",
  "location_id": "uuid-location-456",
  "start_date": "2022-01-01",
  "is_current": true
}
```

**Step 8: Update person details**
```json
// Use: update_person (if needed to modify any fields)
{
  "person_id": "uuid-123",
  "last_interaction_date": "2025-10-14"
}
```

**Step 9: Verify complete profile**
```json
// Use: get_person_details
{"person_id": "uuid-123"}
// Returns: All biographical data, notes, relationships, work, education, residences
```

---

## 9. 📚 Related Resources

- **EVENTS.md** - Event system and event_participants integration
- **LOCATIONS.md** - Location reference for residential/work/education history
- **WORKOUTS.md** - Workout partners and training context
