# Personal Journal Database with MCP Server

**PostgreSQL-based personal journal database optimized for LLM interaction via Model Context Protocol (MCP).**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PostgreSQL 15+](https://img.shields.io/badge/postgresql-15+-blue.svg)](https://www.postgresql.org/)
[![Tests](https://img.shields.io/badge/tests-53%20passing-brightgreen.svg)](./TESTING.md)

## 📋 Table of Contents

- [Overview](#overview)
- [Why This Architecture?](#why-this-architecture)
- [Quick Start](#quick-start)
- [Core Concepts: Event-Centric Design](#core-concepts-event-centric-design)
- [Database Schema](#database-schema)
- [Usage Examples](#usage-examples)
- [MCP Server Tools](#mcp-server-tools)
- [Testing](#testing)
- [Installation & Deployment](#installation--deployment)
- [Troubleshooting](#troubleshooting)

---

## Overview

A complete PostgreSQL-based personal journal system that tracks:

- 💪 **Workouts** - Exercises, sets, reps, weights, progression tracking
- 🍽️ **Meals** - Food items, nutrition, dietary patterns
- 📅 **Events** - Social activities, travel, meetings with people and locations
- 💼 **Work** - Work blocks, productivity tracking
- 👥 **People** - Contacts, relationships, activity partners
- 📍 **Locations** - Places, venues, frequent locations

**Key Features:**
- ✅ LLM-optimized for natural language queries
- ✅ Event-centric architecture (WHO, WHERE, WHEN + specialized WHAT)
- ✅ Production-ready with comprehensive testing (53 tests)
- ✅ **Dual mode support: stdio (Claude Desktop) and HTTP/WebSocket (web clients)**
- ✅ Multiple deployment options (local, VS Code extension, Claude Desktop, Azure)
- ✅ Connection pooling and performance optimization
- ✅ Environment-aware configuration (dev/test/prod)
- ✅ Safe write operations with human-in-the-loop confirmation

---

## Why This Architecture?

### PostgreSQL Over NoSQL

| Feature | This (PostgreSQL) | NoSQL (Cosmos DB) |
|---------|-------------------|-------------------|
| **LLM Query Generation** | ✅ Excellent - Natural SQL | ⚠️ Complex - Custom syntax |
| **Complex Joins** | ✅ Single query | ❌ Multiple queries + app code |
| **Time-Series Analysis** | ✅ Built-in functions | ⚠️ Manual implementation |
| **Aggregations** | ✅ GROUP BY, window functions | ⚠️ Limited aggregation pipeline |
| **Cost for Analytics** | ✅ Predictable | ⚠️ RU-based (can be expensive) |
| **Tool Simplicity** | ✅ One tool handles all | ⚠️ Many specialized tools needed |

### Event-Centric Design

**Events are PRIMARY. Workouts/Meals are SPECIALIZATIONS.**

```
Event (WHO, WHERE, WHEN)
  └─> Specialization (WHAT: workout details, meal items, etc.)
```

**Benefits:**
- 🎯 Natural for LLM understanding: "Worked out at Equinox with Sarah"
- 🔗 Easy to link activities with people and locations
- 📊 Unified querying across all activity types
- 🧹 Clean separation of concerns (timing/location vs. activity details)

### Architecture Layers

```
┌─────────────────────────────────────────────┐
│          LLM (Claude, GPT-4, etc.)          │
│   "Show me my bench press progression"      │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│         MCP Client Connection                │
│  • Stdio (Claude Desktop)                   │
│  • HTTP/WebSocket (Web clients) ← NEW!      │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│            MCP Server                        │
│  ┌─────────────────────────────────────┐   │
│  │  execute_sql_query()                │   │  ← Main tool
│  │  get_exercise_progression()         │   │  ← Helper tools
│  │  get_muscle_group_balance()         │   │
│  │  search_activities_with_people()    │   │
│  └─────────────────────────────────────┘   │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│         Repository Layer                     │
│  ┌─────────────────────────────────────┐   │
│  │ WorkoutsRepository                  │   │
│  │ MealsRepository                     │   │
│  │ EventsRepository                    │   │
│  │ PeopleRepository                    │   │
│  └─────────────────────────────────────┘   │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│      PostgreSQL Database (Azure/Local)       │
│  ┌─────────────────────────────────────┐   │
│  │ Tables: events, workouts, meals...  │   │
│  │ Views: workout_events, meal_events  │   │
│  │ Triggers: auto-update computed stats│   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- **PostgreSQL 15+** (local or Azure)
- **Python 3.10+**
- **pip** for package management

### Installation

**1. Install PostgreSQL**

```bash
# Windows: Download from postgresql.org and install
# Mac: brew install postgresql && brew services start postgresql
# Linux: sudo apt-get install postgresql && sudo systemctl start postgresql
```

**2. Install Python Package**

```bash
cd db-mcp-server
pip install -r requirements.txt
pip install -e .  # Installs 'journal-mcp-server' and 'journal-mcp-http' commands
```

**3. Configure Environment**

```bash
cp .env.example .env
nano .env  # Edit with your database credentials
```

Example `.env`:
```bash
APP_ENV=development
DB_HOST=localhost
DB_PORT=5432
DB_NAME=assistant_db_test
DB_USER=postgres
DB_PASSWORD=your_password
DB_SSL_MODE=prefer
```

**4. Initialize Database**

```bash
python init_db.py init         # Create schema
python init_db.py seed         # (Optional) Add sample data
```

**5. Start Server**

```bash
# Stdio mode (for Claude Desktop, VS Code Extension)
python server.py
# or
journal-mcp-server

# HTTP mode (for web clients, remote access) ← NEW!
python server.py --http
# or
journal-mcp-http
```

**🎉 Done!** Your journal database is ready for LLM queries.

💡 **For complete installation instructions** (including HTTP mode, VS Code extension, Claude Desktop, and Azure deployment), see **[SETUP.md](SETUP.md)**.

---

## Core Concepts: Event-Centric Design

### The Mental Model

**Old Thinking:** "Create a workout"  
**New Thinking:** "Create an EVENT of type workout"

Every activity starts as an **Event** (WHO, WHERE, WHEN), then gets specialized details (WHAT).

### Example: Logging a Workout

User says: *"Worked out at Equinox with Sarah - bench press 3x8 at 185 lbs"*

**Processing Flow:**

1. **Parse**: Extract WHO (Sarah), WHERE (Equinox), WHEN (today), WHAT (workout details)
2. **Resolve Entities**: Get/create Sarah from `people`, Get/create Equinox from `locations`
3. **Create EVENT**: 
   ```sql
   event_type='workout', start_time, location_id, 
   participants=[Sarah with role='participant']
   ```
4. **Create WORKOUT**: 
   ```sql
   event_id, category='STRENGTH', workout_name='Morning Chest'
   ```
5. **Create EXERCISES**: 
   ```sql
   workout_id, exercise_id (bench press), sets=[3x8 @ 185 lbs]
   ```
6. **Confirm**: "✅ Workout saved! Oct 4 @ Equinox (with Sarah)"

### Query Patterns

#### ✅ Correct Patterns

```sql
-- ✅ Join through events for timing/location
SELECT w.*, e.start_time, e.event_date, l.canonical_name as location
FROM workouts w
JOIN events e ON w.event_id = e.id
LEFT JOIN locations l ON e.location_id = l.id
WHERE e.event_date >= '2025-10-01';

-- ✅ Use convenience views (easiest!)
SELECT * FROM workout_events WHERE event_date >= '2025-10-01';
SELECT * FROM meal_events WHERE event_date >= '2025-10-01';

-- ✅ Query by participant
SELECT e.*, w.workout_name
FROM events e
JOIN event_participants ep ON e.id = ep.event_id
JOIN people p ON ep.person_id = p.id
LEFT JOIN workouts w ON e.id = w.event_id
WHERE p.canonical_name ILIKE '%Sarah%'
  AND e.event_type = 'workout';
```

#### ❌ Wrong Patterns

```sql
-- ❌ Workouts don't have start_time/location_id directly
SELECT * FROM workouts WHERE start_time >= '2025-10-01';

-- ❌ Can't create workout without event first
INSERT INTO workouts (workout_name, category) VALUES ('Bench Day', 'STRENGTH');
```

---

## Database Schema

### Core Tables

```
events (PRIMARY)
  ├─ id, event_type, start_time, end_time, event_date
  ├─ location_id → locations
  ├─ title, description, category, tags
  └─ event_participants
       ├─ event_id → events
       ├─ person_id → people
       └─ role ('participant', 'trainer', 'host')

Specializations (all have event_id FK):
├─ workouts → workout_exercises → exercise_sets
├─ meals → meal_items
└─ (events can exist without specialization)

Reference Data:
├─ people (normalized with fuzzy search)
├─ locations (normalized with fuzzy search)
└─ exercises (normalized with muscle groups)
```

### Convenience Views

Pre-joined views make querying easier:

- **`workout_events`** - Workouts + event fields (start_time, location, participants)
- **`meal_events`** - Meals + event fields
- **`events_with_participants`** - Events with participant names

**Usage:**
```sql
SELECT * FROM workout_events 
WHERE event_date = '2025-10-04'
ORDER BY start_time;
```

---

## Usage Examples

### Python API (Repository Layer)

```python
from database import init_database
from repositories import WorkoutsRepository, EventsRepository
from models import EventCreate, WorkoutCreate, EventParticipant, WorkoutCategory

# Initialize
db = await init_database()
events_repo = EventsRepository(db)
workouts_repo = WorkoutsRepository(db)

# Create event with workout (event-first pattern ⭐)
event = EventCreate(
    event_type=EventType.WORKOUT,
    start_time=datetime(2025, 10, 4, 9, 0),
    end_time=datetime(2025, 10, 4, 10, 30),
    location_id=gym_id,
    participants=[EventParticipant(person_id=sarah_id, role="participant")]
)

workout = WorkoutCreate(
    workout_name="Upper Body Strength",
    category=WorkoutCategory.STRENGTH,
    exercises=[
        WorkoutExercise(
            exercise_id=bench_press_id,
            sequence_order=1,
            sets=[
                ExerciseSet(set_number=1, weight_kg=80, reps=8),
                ExerciseSet(set_number=2, weight_kg=85, reps=6),
                ExerciseSet(set_number=3, weight_kg=90, reps=4),
            ]
        )
    ]
)

# Save together (transactional)
created = await workouts_repo.create_with_event(event, workout)

# Access combined data
print(created.event.start_time)  # Event timing
print(created.event.participants)  # WHO
print(created.workout.total_volume_kg)  # Workout specifics
```

### MCP Server (LLM Queries)

```python
from mcp_server import JournalMCPServer

server = JournalMCPServer()
await server.initialize()

# Execute raw SQL
result = await server.execute_sql_query("""
    SELECT * FROM workout_events 
    WHERE event_date >= CURRENT_DATE - INTERVAL '7 days'
    ORDER BY start_time DESC
""")

# Use helper tools
progression = await server.get_exercise_progression("bench press", days_back=90)
balance = await server.get_muscle_group_balance(days_back=30)
activities = await server.search_activities_with_people(
    person_name="Sarah",
    activity_type="workout",
    location="Equinox"
)
```

---

## MCP Server Tools

### � Instructions & Resources

**The MCP server exposes comprehensive documentation via prompts and resources:**

**Main System Instructions (Prompt):**
```javascript
// MCP hosts should call this on initialization:
const instructions = await mcp.getPrompt("journal_system_instructions");
// Returns: Complete system instructions from mcp/prompts/INSTRUCTIONS.md
```

**Domain-Specific Resources:**
```javascript
// List available domain documentation:
const resources = await mcp.listResources();
// Returns: EVENTS, WORKOUTS, MEALS, PEOPLE, LOCATIONS, etc.

// Load specific domain docs:
const eventsDoc = await mcp.readResource("instruction://EVENTS");
const workoutsDoc = await mcp.readResource("instruction://WORKOUTS");
```

**Available Resources:**
- `instruction://EVENTS` - Event management (activities, meetings, social)
- `instruction://WORKOUTS` - Exercise tracking, progression
- `instruction://MEALS` - Meal logging, nutrition
- `instruction://PEOPLE` - Contact management, relationships
- `instruction://LOCATIONS` - Place catalog
- `instruction://TRAVEL` - Commute tracking, routes
- `instruction://ENTERTAINMENT` - Media consumption

**Schema Reference:** Database schema details are in the main INSTRUCTIONS.md file (Database Schema Overview section)

**💡 Note for MCP Hosts:** These instructions are critical for proper tool usage. Load the main prompt on initialization and domain resources as needed.

---

### �🔧 Primary Tool

**`execute_sql_query(query, params=[])`**

Execute queries against the database:
- **Reads (SELECT):** Execute immediately
- **Writes (INSERT/UPDATE/DELETE):** Automatically route to pending confirmation system

### 🛠️ Helper Tools

| Tool | Purpose | Example |
|------|---------|---------|
| `get_database_schema()` | Schema information | Tables, columns, types, row counts |
| `get_exercise_progression(name, days)` | Track exercise progress | Weights, reps, volume over time |
| `get_muscle_group_balance(days)` | Training balance | OVERWORKED/BALANCED/UNDERWORKED |
| `search_activities_with_people(...)` | Find shared activities | Workouts/events with people |
| `get_upcoming_events(days, person)` | Future events | Calendar view |
| `get_day_summary(date)` | Daily summary | Complete day's activities |
| `propose_write_query()` | Propose write operations | Requires human confirmation |
| `confirm_write_query()` | Execute approved writes | After human review |
| `list_pending_writes()` | View pending writes | Review queue |
| `cancel_write_query()` | Cancel pending writes | Remove from queue |

### Common Queries

**"How is my bench press progressing?"**
```python
progression = await server.get_exercise_progression("bench press", days_back=90)
```

**"Which muscle groups am I neglecting?"**
```python
balance = await server.get_muscle_group_balance(days_back=30)
```

**"Show me workouts with Sarah"**
```python
activities = await server.search_activities_with_people(
    person_name="Sarah",
    activity_type="workout"
)
```

---

## Testing

### 🧪 Comprehensive Test Suite

The project includes **53 automated tests** covering all functionality with a real PostgreSQL test database.

**Quick Test Run:**
```bash
python run_tests.py
```

**With Coverage Report:**
```bash
python run_tests.py --coverage  # Generates htmlcov/index.html
```

**What Gets Tested:**
- ✅ Database connectivity and schema validation
- ✅ All CRUD operations (workouts, meals, events)
- ✅ Repository layer functionality
- ✅ Data integrity and foreign key constraints
- ✅ Complex queries and aggregations
- ✅ End-to-end workflows
- ✅ MCP server readiness

**Test Database Isolation:**

The test runner automatically uses a separate `assistant_db_test` database and sets `APP_ENV=test` - your production data is never touched.

**See [TESTING.md](TESTING.md) for complete testing guide.**

---

## Installation & Deployment

### 📦 Installation Options

The Journal MCP Server supports multiple deployment scenarios:

1. **Local Development** - Direct Python execution
2. **VS Code Extension** - Integrated with VS Code MCP
3. **Claude Desktop** - Direct LLM client connection
4. **Azure Cloud** - Production deployment

### Package Installation

Install as a Python package for path-independent usage:

```bash
cd db-mcp-server
pip install -e .
```

This creates a `journal-mcp-server` command in your PATH.

**Verify:**
```bash
journal-mcp-server --version
```

### Configuration Priority

The server uses a **3-tier configuration system**:

1. **Environment Variables** (highest priority) - Set by client (VS Code, Claude Desktop)
2. **`.env` File** (fallback) - For local development
3. **Default Values** (lowest priority) - Hardcoded defaults

**Example: VS Code Extension**

VS Code settings → Environment variables → Server uses those values (`.env` ignored)

**Example: Direct Execution**

No environment variables → Server reads `.env` file → Falls back to defaults

**Key Setting:** `load_dotenv(override=False)` ensures client config always wins!

### 🔗 Complete Setup Guide

For detailed installation instructions covering:
- PostgreSQL installation (Windows/Mac/Linux)
- Database initialization
- VS Code extension setup
- Claude Desktop configuration
- Azure deployment
- Security best practices
- Troubleshooting

**See [INSTALLATION.md](INSTALLATION.md) for the complete guide.**

---

## 🌐 HTTP Mode (Web Client Support)

The server supports **two connection modes**:

### Stdio Mode (Default)
For desktop clients like Claude Desktop and VS Code Extension:
```bash
journal-mcp-server
# or
python server.py
```

### HTTP Mode (New)
For web clients, remote access, and API integrations:
```bash
journal-mcp-http
# or
python server.py --http
```

### HTTP Endpoints

Once running, the HTTP server exposes:

**Health Check:**
```bash
curl http://localhost:3000/health
```

**List Tools (REST):**
```bash
curl http://localhost:3000/listTools
```

**JSON-RPC Endpoint:**
```bash
curl -X POST http://localhost:3000/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list",
    "params": {}
  }'
```

**WebSocket (Real-time):**
```javascript
const ws = new WebSocket('ws://localhost:3000/ws');
ws.send(JSON.stringify({
  jsonrpc: "2.0",
  id: 1,
  method: "tools/call",
  params: {
    name: "get_database_schema",
    arguments: {}
  }
}));
```

### Configuration

Set the HTTP port via environment variable:
```bash
export HTTP_PORT=3000  # Default: 3000
journal-mcp-http
```

### JSON-RPC Methods

HTTP mode supports all MCP protocol methods:
- `tools/list` - List available tools
- `tools/call` - Execute a tool
- `prompts/list` - List prompts
- `prompts/get` - Get prompt content
- `resources/list` - List resources
- `resources/read` - Read resource

### Feature Parity

Both modes use identical handlers - **complete feature parity guaranteed**.

| Feature | Stdio | HTTP |
|---------|-------|------|
| Connection | stdin/stdout | HTTP/WebSocket |
| Use Case | Desktop clients | Web clients, APIs |
| Authentication | Process-level | Add middleware |
| Concurrent Clients | No (1:1) | Yes (many:1) |
| Tool Execution | ✅ Identical | ✅ Identical |

### Security for Production

When deploying HTTP mode publicly:
- Add authentication (JWT, API keys)
- Restrict CORS origins (edit `http_adapter.py`)
- Use HTTPS/WSS with TLS certificates
- Implement rate limiting
- Deploy behind reverse proxy (nginx, traefik)

### Docker Deployment

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -e .
EXPOSE 3000
ENV HTTP_PORT=3000
CMD ["journal-mcp-http"]
```

---

## Troubleshooting

### Can't connect to database

```bash
# Test connection
psql -h localhost -U postgres

# Verify credentials
python show_config.py

# Check if PostgreSQL is running (Windows)
services.msc  # Look for "postgresql"
```

### Schema not initialized

```bash
# Check if tables exist
python -c "from database import *; import asyncio; asyncio.run(list_tables())"

# Reinitialize
python init_db.py reset
```

### Command not found: journal-mcp-server

```bash
# Check installation
pip show journal-mcp-server

# Reinstall
pip uninstall journal-mcp-server
pip install -e /path/to/db-mcp-server

# Add Python Scripts to PATH (Windows)
# C:\Users\<username>\AppData\Local\Programs\Python\Python3X\Scripts
```

### Wrong database being used

```bash
python show_config.py  # Shows current APP_ENV and database
export APP_ENV=development  # Or test/production
```

### Test failures

```bash
# Run with verbose output
pytest tests/ -v -s --tb=long

# Verify PostgreSQL is running
# Ensure test database exists
python run_tests.py --setup-only
```

---

## Development

### 🔧 Utility Commands

```bash
# Configuration
python show_config.py           # Verify current config

# Database management
python init_db.py init          # Create schema
python init_db.py seed          # Add sample data
python init_db.py reset         # Drop + recreate + seed

# Testing
python run_tests.py             # Run all tests
python run_tests.py --coverage  # With coverage report

# Code quality
black .                         # Format code
ruff check .                    # Lint
mypy .                          # Type check
```

### 📦 Repository Methods

**Event-First Pattern (Recommended ⭐):**
```python
await workouts_repo.create_with_event(event, workout)
await meals_repo.create_with_event(event, meal)
```

**Standard CRUD:**
```python
await repo.get_by_id(id)
await repo.list_by_date_range(start_date, end_date)
await repo.update(id, updates)
await repo.delete(id)
```

---

## Documentation

| Document | Purpose |
|----------|---------|
| **[README.md](README.md)** | This file - Complete project overview |
| **[INSTALLATION.md](INSTALLATION.md)** | Complete installation guide |
| **[TESTING.md](TESTING.md)** | Testing guide (53 tests, coverage reports) |
| **[mcp/prompts/INSTRUCTIONS.md](mcp/prompts/INSTRUCTIONS.md)** | LLM system prompt (auto-loaded by MCP) |

---

## License & Support

**License:** MIT

**Repository:** [github.com/svarun115/JournalMCPServer](https://github.com/svarun115/JournalMCPServer)

**Issues:** Open a GitHub issue for bugs or feature requests

---

**Built with ❤️ for personal journaling and LLM interaction**
