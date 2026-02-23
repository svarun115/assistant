# Entertainment - Complete Reference

**Media consumption tracking: movies, TV shows, podcasts, live performances, gaming, reading.**

---

## Quick Reference

### Available Entertainment Tools

| Tool | Purpose | When to Use |
|------|---------|-------------|
| SQL queries | Get media consumption history, ratings analysis, viewing patterns | Via `execute_sql_query()` |

### Entertainment Types

- `movie` - Films, documentaries
- `tv_show` - TV series, episodes
- `youtube` - YouTube videos
- `podcast` - Podcast episodes
- `live_performance` - Concerts, theater, comedy shows
- `gaming` - Video games, board games
- `reading` - Books, articles, magazines
- `streaming` - Streaming content (Twitch, etc.)

---

## 2. 📊 Available Tools

**SQL Queries and Write Tool:**

### SQL Query Patterns

**All entertainment queries use `execute_sql_query()`**

### Get Entertainment History
```sql
SELECT 
    e.id, e.entertainment_type, e.title,
    ent.watched_date,
    ent.rating,
    EXTRACT(EPOCH FROM (ev.end_time - ev.start_time))/60 as duration_minutes,
    l.canonical_name as location,
    ent.notes
FROM entertainment ent
JOIN events ev ON ent.event_id = ev.id
LEFT JOIN locations l ON ev.location_id = l.id
WHERE ev.start_time >= CURRENT_DATE - INTERVAL '90 days'
ORDER BY ent.watched_date DESC
LIMIT 20;
```

### Filter by Entertainment Type
```sql
SELECT 
    e.entertainment_type,
    e.title,
    ent.watched_date,
    ent.rating,
    EXTRACT(EPOCH FROM (ev.end_time - ev.start_time))/60 as duration_minutes,
    ent.notes
FROM entertainment ent
JOIN events ev ON ent.event_id = ev.id
WHERE ent.entertainment_type = 'movie'
  AND ev.start_time >= CURRENT_DATE - INTERVAL '365 days'
ORDER BY ent.watched_date DESC;
```

### Get Highest Rated Entertainment
```sql
SELECT 
    e.entertainment_type,
    e.title,
    ent.watched_date,
    ent.rating,
    ent.notes
FROM entertainment ent
JOIN events ev ON ent.event_id = ev.id
WHERE ent.rating >= 8
  AND ev.start_time >= CURRENT_DATE - INTERVAL '180 days'
ORDER BY ent.rating DESC, ent.watched_date DESC;
```

### Entertainment Consumption Stats
```sql
SELECT 
    ent.entertainment_type,
    COUNT(*) as count,
    ROUND(AVG(COALESCE(ent.rating, 0))::numeric, 2) as avg_rating,
    ROUND(AVG(ent.duration_minutes)::numeric, 2) as avg_duration_minutes,
    SUM(ent.duration_minutes) as total_minutes
FROM entertainment ent
JOIN events ev ON ent.event_id = ev.id
WHERE ev.start_time >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY ent.entertainment_type
ORDER BY count DESC;
```

---

## Tool Usage

**Typical workflows:**
- "What have I been watching?" → Use SQL query above with 30-day filter
- "What movies did I watch?" → Use SQL query filtered by entertainment_type='movie'
- "Show me my favorites" → Use SQL query with rating >= 8

**SQL-First Philosophy:** Use `execute_sql_query()` with the patterns above for all data retrieval.

---

## 4. 📝 Journal Extraction Guide

### Extraction Pattern

When extracting entertainment information from journal entries, identify:

1. **Event details (WHO, WHERE, WHEN)**
   - Start time and duration
   - Location (theater, venue, or "Home")
   - Participants (viewing/playing companions)
   - Event title and description

2. **Entertainment specifics (WHAT)**
   - Entertainment type (movie, tv_show, gaming, etc.)
   - Title of content
   - Personal rating (1-10)
   - Genre/category
   - Platform/venue
   - Review notes and thoughts

3. **Tool to use**: `log_entertainment` with event linkage

### Example Extractions

**Movie at theater:**
```
Journal: "Watched Inception with Sarah at AMC. Mind-blowing! Favorite scene was the rotating hallway fight."

Event:
  event_type = 'entertainment'
  start_time = 19:00:00
  title = "Watched Inception at AMC"
  notes = "Mind-blowing! Favorite scene was the rotating hallway fight."
  tags = ['sci_fi', 'thriller', 'theater']
  location_id = "uuid-from-search-or-create_location"

Entertainment:
  entertainment_type = 'movie'
  title = "Inception"
  external_reference = "https://www.imdb.com/title/tt1375666/"

Participants: Sarah
```

**TV show binge:**
```
Journal: "Watched 3 episodes of Breaking Bad tonight. Season 5 is intense!"

Event:
  event_type = 'entertainment'
  start_time = 20:00:00
  end_time = 22:30:00
  title = "Breaking Bad S5 binge"
  notes = "Watched 3 episodes. Season 5 is intense!"
  tags = ['tv_show', 'drama', 'binge', 'netflix']
  location_id = "uuid-for-home-location"  // Optional; omit if unknown

Entertainment:
  entertainment_type = 'tv_show'
  title = "Breaking Bad"
  external_reference = "https://www.imdb.com/title/tt0903747/"
```

**Concert:**
```
Journal: "Went to Taylor Swift concert at MetLife Stadium. Amazing show! She played all my favorites."

Event:
  event_type = 'entertainment'
  start_time = 19:30:00
  title = "Taylor Swift concert at MetLife Stadium"
  notes = "Amazing show! She played all my favorites."
  tags = ['concert', 'live_music', 'pop']
  location_id = "uuid-from-search-or-create_location"

Entertainment:
  entertainment_type = 'live_performance'
  title = "Taylor Swift - Eras Tour"
  external_reference = null
```

**Reading:**
```
Journal: "Finished reading Atomic Habits today. Great book on habit formation!"

Event:
  event_type = 'entertainment'
  start_time = 14:00:00
  title = "Finished reading Atomic Habits"
  notes = "Great book on habit formation! Lots of practical advice."
  tags = ['reading', 'self_help', 'productivity']
  location_id = "uuid-for-home-location"  // Optional; omit if unknown

Entertainment:
  entertainment_type = 'reading'
  title = "Atomic Habits"
  external_reference = null
```

**Gaming:**
```
Journal: "Played Zelda with Mike for a few hours. Got through 3 dungeons!"

Event:
  event_type = 'entertainment'
  start_time = 15:00:00
  end_time = 18:00:00
  title = "Zelda gaming session"
  notes = "Got through 3 dungeons! Finally beat the water temple."
  tags = ['gaming', 'multiplayer', 'switch']
  location_id = "uuid-for-home-location"  // Optional; omit if unknown

Entertainment:
  entertainment_type = 'gaming'
  title = "The Legend of Zelda: Tears of the Kingdom"
  external_reference = null

Participants: Mike
```

### Inference Rules

**Entertainment type from context:**
- "watched [movie]", "saw [movie]" → `movie`
- "watched [show]", "episode", "season" → `tv_show`
- "concert", "show", "performance" → `live_performance`
- "played [game]", "gaming" → `gaming`
- "read", "reading", "book" → `reading`
- "listened to [podcast]" → `podcast`
- "youtube", "video" → `youtube`

**Genre/tags from content:**
- Extract genre from title/context (sci-fi, drama, comedy, etc.)
- Add platform tags (netflix, hbo, theater, spotify)
- Add context tags (binge, rewatch, first_time)

**Location inference:**
- Theater/venue name mentioned → Resolve/create a location, then use `location_id`
- "at home", "netflix" → Use Home `location_id` if you have one; otherwise omit location
- Default → Omit location if you can't confidently resolve it

---

## 5. 🚨 Important Notes

### Minimalist Design

**Store in specialized table:**
- ✅ entertainment_type (movie, tv_show, etc.)
- ✅ title (name of content)
- ✅ external_reference (IMDB, YouTube link, etc.)

**Store in event.title:**
- ✅ Experience description
- Example: "Watched Inception at AMC", "Breaking Bad S5E12"

**Store in event.notes:**
- ✅ Thoughts, opinions, reviews
- ✅ Favorite moments, memorable scenes
- ✅ Ratings/recommendations ("9/10", "Highly recommend")

**Store in event.tags:**
- ✅ Genres (`sci_fi`, `comedy`, `drama`, `thriller`)
- ✅ Platforms (`netflix`, `hbo`, `theater`, `youtube`)
- ✅ Context (`rewatch`, `binge`, `first_time`, `highly_recommend`)

**Do NOT store:**
- ❌ Plot summaries (use IMDB/Wikipedia)
- ❌ Cast lists (use external databases)
- ❌ Detailed ratings systems (use external review sites)
- ❌ Full episode guides (not journaling data)

### Validation Rules

- Event with event_type='entertainment' MUST have entertainment entry
- Enforced by trigger: `validate_event_specialized_table`
- Cascade deletion: Deleting event deletes entertainment record

### Special Cases

**TV Shows:**
- Can track per-episode or per-session (binge)
- Use event.title to specify season/episode (e.g., "Breaking Bad S5E12")
- Or just title for binge sessions (e.g., "Breaking Bad S5 binge")

**Rewatches:**
- Use tag `rewatch` to mark rewatched content
- Original watch and rewatch are separate events

**Social Viewing:**
- Add participants via event_participants
- Use role='companion' or NULL

**Live Performances:**
- Include venue in location
- Note artist/performer in entertainment.title
- Can include setlist details in notes

---

## 6. 📚 Related Resources

- **EVENTS.md** - Event system architecture and entertainment event creation
- **PEOPLE_SYSTEM.md** - For tracking viewing companions
- **LOCATIONS_TABLE.md** - Theater, venue, and location reference
- **TOOLS_WRITE.md** - Creating entertainment events with write tools
