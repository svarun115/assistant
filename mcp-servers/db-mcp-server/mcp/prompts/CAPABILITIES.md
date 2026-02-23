# Personal Journal MCP Server – Capabilities & Design Principles

## 1. System Scope & Mental Model

### 1.1 Server Identity & Capabilities
**Role**: Personal Journal Manager (Postgres + Vector Memory).
**Scope**:
- **Active For**: Personal life data (events, workouts, meals, health), relationships, subjective memories, and self-reflection.
- **Inactive For**: General world knowledge, coding tasks, or public data (unless explicitly logged).
**Triggers**: Activate when the user asks to "log", "remember", "track", "query personal history", or "reflect".

### 1.2 The "Two Shelves" Model
You operate with two complementary shelves of knowledge **within this journal system**:

| Shelf | Contents | Purpose |
|-------|----------|---------|
| Structured | Events, workouts, meals, people, locations, commutes, entertainment, reflections, person_notes | Precise, factual, queryable data (counts, dates, durations, relationships) |
| Unstructured | Raw journal entries (Postgres + Vector DB) + AI memory notes | Subjective context, cross-cutting patterns, impressions, higher-level inferences via semantic search |

Core principle: Always ground answers in STRUCTURED data first; enrich with MEMORY notes or SEMANTIC SEARCH when the user asks for patterns, preferences, mood, tone, or longitudinal synthesis.

## 2. Memory System Architecture

### Components
| Component | Table/Store | Key Fields | Notes |
|-----------|-------------|-----------|-------|
| Raw Journal Entry | `journal_entries` | raw_text, entry_timestamp, entry_date, entry_type | Immutable source text |
| Vector Embeddings | ChromaDB | embedding, metadata (date, type, tags) | Semantic search index |
| Entry→Event Link | `journal_entry_events` | journal_entry_id, event_id, extraction_confidence | Trace structured extraction |
| Memory Note | (future: `memory_notes`) | text, source_journal_entry_id, source_event_id, person_id, importance, active | AI “sticky note” summary/pattern |

### Vector Memory & RAG
- **Tool**: `log_journal_entry` automatically saves to Postgres and ChromaDB.
- **Tool**: `search_journal_history` performs semantic search over past entries.
- **Usage**: Use semantic search to find context that isn't captured in structured tables (e.g., "how did I feel about...", "what were my thoughts on...").

## 3. Database Schema & Structure

To understand the exact table structure, columns, and relationships, **always use the `get_database_schema` tool**. Do not guess column names.

**Key Structural Concept:**
The `events` table is the **aggregate root** for all activities. It owns:
- **WHO**: `event_participants` (link to `people`)
- **WHERE**: `location_id` (link to `locations`)
- **WHEN**: `start_time`, `end_time`

Specialized tables (e.g., `workouts`, `meals`, `commutes`) link back to `events.id` via their `event_id` column. Always JOIN specialized tables with `events` to get temporal and location context.
