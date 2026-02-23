# Journal & Memory - Complete Reference

**Reference for the unstructured knowledge shelf: Journal Entries, Vector Search, and Memory.**

---

## 1. Quick Reference

### What is the Journal System?
The Journal System captures raw, unstructured text (your "stream of consciousness") and indexes it for semantic retrieval. Unlike structured tables (Events, Workouts) which answer "How many?", the Journal System answers "How did I feel?" or "What was the context?".

### Core Components
| Component | Storage | Purpose |
|-----------|---------|---------|
| **Journal Entries** | Postgres `journal_entries` | Immutable record of what you wrote. |
| **Vector Index** | ChromaDB | Semantic embeddings of entries for "fuzzy" search. |
| **Links** | `journal_entry_events` | Connects raw text to structured events. |

---

## 2. Tools

### `log_journal_entry`
**Purpose**: The primary ingestion tool.
- **Actions**:
    1. Saves raw text to Postgres `journal_entries`.
    2. Generates embeddings and saves to ChromaDB.
    3. Returns a `journal_entry_id`.
- **Usage**: Call this *first* when processing a user's raw input.

### `search_journal_history`
**Purpose**: Semantic search over past entries with optional metadata filtering.
- **Mechanism**: Converts query to vector -> Finds nearest neighbors in ChromaDB.
- **Optional Filters**:
    - `start_date` / `end_date`: Search within a date range (e.g., only 2024 entries)
    - `entry_types`: Filter by entry type(s) - `["journal", "reflection", "idea"]`
    - `tags`: Filter by tags - entries must have at least one matching tag
- **Use Cases**:
    - Finding subjective context ("How did I feel about the marathon?")
    - Finding patterns not in SQL ("When do I usually feel stressed?")
    - Retrieving vague memories ("I think I went to a place with red walls...")
    - Time-scoped searches ("What was I thinking about in Q1 2024?")
    - Type-specific searches ("Show me only my project ideas")
    - Tag-based searches ("Find all my fitness and health reflections")

---

## 3. Database Schema

### `journal_entries`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary Key |
| `raw_text` | TEXT | The full content of the entry |
| `entry_date` | DATE | The logical date of the entry |
| `entry_timestamp` | TIMESTAMP | When it happened (defaults to now) |
| `source` | VARCHAR | e.g., "user_input", "import" |

### `journal_entry_events`
**The Bridge between Unstructured and Structured data.**
| Column | Type | Description |
|--------|------|-------------|
| `journal_entry_id` | UUID | FK to `journal_entries` |
| `event_id` | UUID | FK to `events` |
| `context` | TEXT | Optional context for the link |

---

## 4. Best Practices

### Hybrid Retrieval (The "Two Shelves" Approach)
To answer complex questions, combine methods:
1. **SQL (Structured)**: "Show me workouts from last week." (Precise)
2. **Vector (Unstructured)**: "How was my energy level?" (Semantic)
3. **Synthesis**: "You ran 3 times (SQL), but noted feeling 'sluggish' in 2 of them (Vector)."

### Writing Entries
- **Detail is key**: The more descriptive the text, the better the semantic search.
- **Timestamps**: Always try to capture the correct `entry_date`.

### Linking
- After creating a structured Event (e.g., a Workout) from a Journal Entry, **always** create a link in `journal_entry_events`. This allows you to trace the source of the data later.
