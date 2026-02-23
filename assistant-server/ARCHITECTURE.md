# Journal Agent Orchestrator — Architecture

> **Status:** Draft for validation  
> **Last Updated:** 2026-01-01

## Overview

A stateful, multi-turn conversational agent for personal journaling that orchestrates multiple MCP servers while maintaining session context and applying domain-specific workflows.

```
┌─────────────────────────────────────────────────────────────────┐
│                      Client (Mobile App / CLI)                  │
└───────────────────────────────┬─────────────────────────────────┘
                                │ HTTP/WebSocket
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Agent Orchestrator                          │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Timeline Skeleton Builder                    │  │
│  │  • Fetches Garmin, Gmail, DB events for target date       │  │
│  │  • Synthesizes unified view with confidence scores        │  │
│  │  • Identifies gaps (unaccounted time blocks)              │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                 Conversation Manager                      │  │
│  │  • Session state (mode, target_date, skeleton, gaps)      │  │
│  │  • Turn history (recent full, older distilled)            │  │
│  │  • Context builder for LLM                                │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   Skills Loader                           │  │
│  │  • Reads .claude/skills/*/SKILL.md                        │  │
│  │  • Injects relevant skills based on session state         │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   Agent Core                              │  │
│  │  • LLM client (Claude / OpenAI / Ollama)                  │  │
│  │  • Agentic loop (tool calls, responses)                   │  │
│  │  • MCP Tool Bridge (dynamic tool discovery)               │  │
│  └───────────────────────────────────────────────────────────┘  │
└───────────────────────────────┬─────────────────────────────────┘
                                │ MCP Protocol (HTTP)
        ┌───────────┬───────────┼───────────┬───────────┐
        ▼           ▼           ▼           ▼           ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
   │journal- │ │ garmin  │ │  gmail  │ │splitwise│ │ google- │
   │   db    │ │         │ │         │ │         │ │ places  │
   └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘
      Data &     Fitness     Email       Expenses    Location
     Events      Metrics    Receipts    Splitting    Lookup
```

---

## Core Principles

| Principle | Description |
|-----------|-------------|
| **Friendly always** | Tone is conversational and supportive, regardless of task |
| **Skeleton-first** | Build unified timeline from all sources before asking user |
| **Context-first** | Fetch relevant context before responding or asking |
| **Entity resolution** | Always search before create; never duplicate |
| **Session-aware** | Intent derives from conversation history, not just current message |
| **Writes are explicit** | Only log/create when clear intent; never speculative |
| **Gaps are visible** | Show user what's unknown, let them fill in |
| **Approximate over brittle** | Accept "around noon" vs demanding exact times |
| **Skills in orchestrator** | Domain knowledge lives here, not in MCP servers |
| **MCP = dumb pipes** | Servers provide data/actions, orchestrator provides intelligence |

---

## Timeline Skeleton

When user starts logging or querying a specific date, build a unified view from all sources.

### Data Sources

| Source | Data | Confidence |
|--------|------|------------|
| **Garmin** | Workouts, sleep, wake time | High |
| **Gmail** | Transaction receipts, bookings | Medium |
| **Journal DB** | Already-logged events | High (user confirmed) |
| **Splitwise** | Shared expenses | Medium |

### Skeleton Structure

```python
@dataclass
class TimelineSkeleton:
    date: date
    blocks: list[TimeBlock]
    gaps: list[TimeGap]
    unplaced: list[AnchorEvent]  # Receipts/events not yet placed in timeline
    
@dataclass
class TimeBlock:
    start_time: datetime
    end_time: datetime | None
    block_type: str           # "workout", "meal", "work", "sleep", "commute", etc.
    title: str
    source: str               # "garmin", "gmail", "db", "inferred"
    confidence: Confidence
    db_event_id: str | None   # If already logged in DB
    external_id: str | None   # Garmin activity ID, etc.
    details: dict

@dataclass
class TimeGap:
    start_time: datetime
    end_time: datetime
    likely_type: str | None   # "lunch", "commute", "unknown"
    duration_minutes: int

@dataclass
class AnchorEvent:
    timestamp: datetime
    event_type: str           # "receipt", "transaction"
    source: str
    description: str          # "Swiggy ₹450", "Uber ₹180"
    
class Confidence(Enum):
    HIGH = "high"             # Device-confirmed (Garmin GPS, DB logged)
    MEDIUM = "medium"         # Receipt/transaction anchored
    LOW = "low"               # Inferred or backfilled
```

### Example Skeleton

```
Timeline for Dec 31, 2025
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

06:45-07:30  🏃 Morning Run (8K)              [Garmin] ✓ Logged
07:30-09:00  ❓ Gap (1h 30m)
09:00-12:30  💼 Work from office              [DB] ✓ Logged
12:30-14:00  ❓ Gap (1h 30m) — likely lunch
14:00-18:00  💼 Work from office              [DB] ✓ Logged  
18:00-19:00  ❓ Gap (1h)
19:15        💳 Uber ₹180                     [Gmail] not placed
19:45        💳 Swiggy ₹450                   [Gmail] not placed
20:00-22:00  ❓ Gap (2h)
22:30        😴 Sleep start                   [Garmin]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Gaps: 3 blocks (5h total)
Unplaced: 2 transactions
```

### Building the Skeleton

```python
async def build_skeleton(self, target_date: date) -> TimelineSkeleton:
    # Fetch from all sources in parallel
    garmin_data, gmail_data, db_events = await asyncio.gather(
        self._fetch_garmin(target_date),
        self._fetch_gmail(target_date),
        self._fetch_db_events(target_date),
    )
    
    # Merge into unified timeline
    blocks = []
    
    # Add Garmin activities (high confidence)
    for activity in garmin_data.activities:
        blocks.append(TimeBlock(
            start_time=activity.start,
            end_time=activity.end,
            block_type="workout",
            source="garmin",
            confidence=Confidence.HIGH,
            external_id=activity.id,
            db_event_id=self._find_linked_event(db_events, activity.id),
        ))
    
    # Add DB events (high confidence, already logged)
    for event in db_events:
        if not self._already_in_blocks(blocks, event):
            blocks.append(TimeBlock(
                start_time=event.start_time,
                end_time=event.end_time,
                block_type=event.event_type,
                source="db",
                confidence=Confidence.HIGH,
                db_event_id=event.id,
            ))
    
    # Sort by time
    blocks.sort(key=lambda b: b.start_time)
    
    # Identify gaps
    gaps = self._find_gaps(blocks, garmin_data.wake_time, garmin_data.sleep_time)
    
    # Collect unplaced receipts
    unplaced = self._find_unplaced_receipts(gmail_data, blocks)
    
    return TimelineSkeleton(date=target_date, blocks=blocks, gaps=gaps, unplaced=unplaced)
```

---

## Conversation Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Message                             │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│              Conversation Manager: Update History               │
│              Extract session state from history                 │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Is this journal-related?                     │
│                                                                 │
│  Journal-related:                                               │
│  • Life events, activities, meals, workouts                     │
│  • People, relationships, memories                              │
│  • Places, travel, commutes                                     │
│  • Health, sleep, reflections                                   │
│  • Questions about any of the above                             │
│                                                                 │
│  NOT journal-related:                                           │
│  • General knowledge questions                                  │
│  • Coding help, math, etc.                                      │
│  • Greetings (unless continuing a session)                      │
└───────────────────┬─────────────────────┬───────────────────────┘
                    │                     │
              Journal-related        Not related
                    │                     │
                    ▼                     ▼
┌───────────────────────────────┐  ┌──────────────────────────────┐
│     Context Fetching          │  │   Friendly chat response     │
│                               │  │   (no tools, no DB access)   │
│  Based on message + session:  │  └──────────────────────────────┘
│  • Garmin data for date       │
│  • Gmail receipts for date    │
│  • Recent related events      │
│  • People mentioned           │
│  • Locations mentioned        │
└───────────────┬───────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Entity Resolution                            │
│                                                                 │
│  For each mentioned entity:                                     │
│  • People: SQL search by name + aliases, check relationships    │
│  • Locations: Search by name, get place_id for public venues    │
│  • Activities: Match to Garmin by time/type/distance            │
│                                                                 │
│  If ambiguous: Ask ONE clarifying question                      │
│  If unresolved: Mark as pending in session state                │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Determine Intent                             │
│                                                                 │
│  Uses: Current message + Session state + History                │
│                                                                 │
│  READ (Query/Discuss):                                          │
│  • "When did I last..."                                         │
│  • "How many times..."                                          │
│  • "Who is..."                                                  │
│  • "Tell me about..."                                           │
│                                                                 │
│  WRITE (Log):                                                   │
│  • "I had lunch with..."                                        │
│  • "Yesterday I ran..."                                         │
│  • Continuation of active logging session                       │
│  • "Sarah's birthday is..." (person update)                     │
│                                                                 │
│  Session state can override message-level ambiguity:            │
│  • If session.mode == "logging" → lean toward WRITE             │
│  • If session has pending_events → likely continuing            │
└───────────────┬─────────────────┬───────────────────────────────┘
                │                 │
            READ only         WRITE intent
                │                 │
                ▼                 ▼
┌───────────────────────┐  ┌──────────────────────────────────────┐
│  Query & Respond      │  │  Create/Update Records               │
│  • SQL queries        │  │  • Events, meals, workouts           │
│  • Semantic search    │  │  • People, locations                 │
│  • Garmin stats       │  │  • Link to Garmin (mandatory cardio) │
│  • Present findings   │  │  • Confirm before committing         │
└───────────────────────┘  └──────────────────────────────────────┘
                │                 │
                └────────┬────────┘
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              Conversation Manager: Store Turn                   │
│              Update session state from response                 │
│              Distill if needed                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Conversation Manager

### Session State

```python
@dataclass
class SessionState:
    mode: Literal["idle", "logging", "querying"]
    target_date: date | None           # Date being logged/queried
    skeleton: TimelineSkeleton | None  # Unified view of the day
    pending_entities: list[PendingEntity]  # Unresolved names/places
    pending_events: list[PartialEvent]     # Partially built events
    turn_count: int
    
@dataclass
class PendingEntity:
    mention: str           # "Sarah", "the gym", "that Thai place"
    entity_type: str       # "person", "location", "activity"
    candidates: list[str]  # Possible matches from DB
    resolved_id: str | None

@dataclass  
class PartialEvent:
    event_type: str        # "meal", "workout", "generic"
    known_fields: dict     # What we know so far
    missing_fields: list   # What we still need
```

### Turn History

```python
@dataclass
class Turn:
    user_message: str
    assistant_response: str
    tool_calls: list[ToolCall]
    timestamp: datetime

class ConversationManager:
    session_state: SessionState
    recent_turns: list[Turn]       # Last N turns (full detail)
    distilled_summary: str         # Compressed older history
    
    # Configuration
    MAX_RECENT_TURNS = 5
    DISTILL_AFTER_TURNS = 10
```

### Distillation Strategy

| Turn Age | Treatment |
|----------|-----------|
| 1-5 | Full messages (need detail for context) |
| 6-15 | Summarized by LLM ("User logged workout, mentioned Sarah") |
| 16+ | Dropped (information already in DB if logged) |

### Context Builder

For each LLM call, builds:

```
┌──────────────────────────────────────────────────────────────┐
│ SYSTEM PROMPT                                                │
│ ├── Base personality (always present, ~200 tokens)           │
│ ├── Session state summary (~100 tokens)                      │
│ │   "Currently logging for Dec 31. 3 gaps remaining."        │
│ ├── Timeline skeleton summary (if logging mode)              │
│ │   "Known: run 6:45am, work 9-6. Gaps: 7:30-9am, lunch..."  │
│ └── Active skill(s) based on mode (~500-2000 tokens)         │
│     • journal-logging if mode == "logging"                   │
│     • journal-querying if mode == "querying"                 │
│     • journal-entities if pending_entities                   │
│     • journal-garmin if workout mentioned                    │
├──────────────────────────────────────────────────────────────┤
│ DISTILLED HISTORY (if any)                                   │
│ "Earlier in session: User confirmed morning workout.         │
│  Logged lunch with Sarah at Blue Tokai."                     │
├──────────────────────────────────────────────────────────────┤
│ RECENT TURNS (full messages)                                 │
│ [user]: "Then I had coffee with mom"                         │
│ [assistant]: "Was this at home or did you go out?"           │
│ [user]: "We went to Starbucks near her place"                │
├──────────────────────────────────────────────────────────────┤
│ TOOLS                                                        │
│ [88 dynamically discovered MCP tools]                        │
└──────────────────────────────────────────────────────────────┘
```

---

## Skills Loader

### Directory Structure

```
.claude/skills/
├── journal-logging/
│   ├── SKILL.md              # Main instructions
│   ├── EXERCISE-RESOLUTION.md
│   ├── SECONDHAND-EVENTS.md
│   └── PITFALLS.md
├── journal-querying/
│   ├── SKILL.md
│   └── QUERY-STRATEGY.md
├── journal-maintenance/
│   └── SKILL.md
├── journal-entities/
│   ├── SKILL.md
│   └── FAMILY-TERMS.md
├── journal-garmin/
│   └── SKILL.md
├── journal-gmail/
│   └── SKILL.md
└── journal-sources/
    └── SKILL.md
```

### Loading Strategy

```python
class SkillsLoader:
    skills_dir: Path
    cached_skills: dict[str, str]
    
    def load_skill(self, name: str) -> str:
        """Load SKILL.md content, cache for session."""
        
    def get_relevant_skills(self, session: SessionState) -> str:
        """Return concatenated skills based on session state."""
        
        skills = []
        
        # Always include base if journal-related
        if session.mode in ("logging", "querying"):
            skills.append("journal-entities")  # Entity resolution always relevant
            skills.append("journal-sources")   # Source priority always relevant
        
        # Mode-specific
        if session.mode == "logging":
            skills.append("journal-logging")
            if has_workout_mention(session):
                skills.append("journal-garmin")
            if session.context_fetched:
                skills.append("journal-gmail")
                
        elif session.mode == "querying":
            skills.append("journal-querying")
            
        return self._combine_skills(skills)
```

---

## Agent Core

### Agentic Loop

```python
async def run_turn(self, user_message: str) -> str:
    # 1. Update conversation with user message
    self.conversation.add_user_message(user_message)
    
    # 2. Build context for LLM
    system_prompt = self._build_system_prompt()
    messages = self.conversation.get_messages_for_llm()
    tools = self.mcp_bridge.to_anthropic_tools()  # or openai format
    
    # 3. Agentic loop
    while True:
        response = await self.llm.chat(system_prompt, messages, tools)
        
        if response.has_tool_calls():
            # Execute tools via MCP bridge
            tool_results = await self._execute_tools(response.tool_calls)
            messages.append(response)
            messages.append(tool_results)
            continue
        else:
            # Final response
            break
    
    # 4. Update conversation with assistant response
    self.conversation.add_assistant_response(response, tool_calls)
    
    # 5. Update session state based on what happened
    self._update_session_state(response, tool_calls)
    
    # 6. Distill if needed
    if self.conversation.should_distill():
        await self._distill_history()
    
    return response.text
```

### Session State Extraction

After each turn, analyze tool calls and response to update session:

```python
def _update_session_state(self, response, tool_calls):
    # Detect mode changes
    if any(tc.name.startswith("create_") for tc in tool_calls):
        self.session.mode = "logging"
    if any(tc.name == "execute_sql_query" for tc in tool_calls):
        self.session.mode = "querying"
    
    # Track resolved entities
    for tc in tool_calls:
        if tc.name in ("create_person", "create_location"):
            # Mark entity as resolved
            self._resolve_pending_entity(tc.arguments)
    
    # Detect session end
    if "that's all" in response.text.lower() or "done" in response.text.lower():
        self.session.mode = "idle"
        self.session.pending_events.clear()
```

---

## MCP Tool Bridge

### Responsibilities

1. **Dynamic Discovery** — Connect to configured servers, list tools
2. **Format Conversion** — Convert MCP schemas to Anthropic/OpenAI formats
3. **Tool Routing** — Route tool calls to correct MCP server
4. **Resilience** — Skip unavailable servers, continue with available

### Tool Call Flow

```
LLM: "Call create_meal with {...}"
         │
         ▼
┌─────────────────────────────────────┐
│ MCP Bridge                          │
│ 1. Find which server owns the tool  │
│ 2. Get session for that server      │
│ 3. Call session.call_tool()         │
│ 4. Parse MCP result                 │
│ 5. Return to agent                  │
└─────────────────────────────────────┘
         │
         ▼
    journal-db MCP server
```

---

## Example Conversation

### First time logging a day

```
USER: Adding journal entry for yesterday

AGENT: [Internal: Build skeleton for Dec 31 from Garmin + Gmail + DB]
       [Skeleton shows: run at 6:45, gaps 7:30-9, 12:30-2, 6-10pm, 
        unplaced: Uber ₹180 at 7:15pm, Swiggy ₹450 at 7:45pm]
       
       Here's what I already know about Dec 31:
       
       ✓ 🏃 Morning run at 6:45am (8K, 45 min) — from Garmin
       ✓ 😴 Sleep at 10:30pm — from Garmin
       
       Unplaced transactions:
       • Uber ₹180 at 7:15pm
       • Swiggy ₹450 at 7:45pm
       
       Gaps to fill: morning after run, lunch, evening.
       
       Tell me about your day!

USER: After the run I had breakfast at home, then worked from office. 
      Lunch was with Sarah from work at Blue Tokai.

AGENT: [Internal: Resolve "Sarah from work" → Sarah Menon]
       [Internal: Resolve "Blue Tokai" → search places near office]
       
       Got it! The Blue Tokai on MG Road near office?

USER: Yes

AGENT: [Internal: Creates breakfast, work, lunch events]
       
       Logged:
       • 🍳 Breakfast at home
       • 💼 Work from office  
       • 🍽️ Lunch at Blue Tokai with Sarah Menon
       
       What about the evening? I see an Uber and Swiggy order around 7pm.

USER: Oh yeah, took Uber to mom's place. We ordered Swiggy for dinner.

AGENT: [Internal: Resolve "mom" → query parent relationship]
       [Internal: Places the Uber and Swiggy receipts]
       
       Logged:
       • 🚗 Commute to mom's place (Uber)
       • 🍽️ Dinner with mom (Swiggy)
       
       Anything else for Dec 31?

USER: That's it!

AGENT: All set! Dec 31 complete — 6 events logged, no gaps remaining 🎉
```

### Revisiting a day to add more

```
USER: I forgot to add something for yesterday

AGENT: [Internal: Build skeleton — now includes previously logged events]
       
       Here's what's logged for Dec 31:
       
       ✓ 🏃 Morning run (6:45am)
       ✓ 🍳 Breakfast at home
       ✓ 💼 Work from office
       ✓ 🍽️ Lunch at Blue Tokai with Sarah
       ✓ 🚗 Commute to mom's
       ✓ 🍽️ Dinner with mom
       
       What did you want to add?

USER: I had a call with my manager in the afternoon

AGENT: [Internal: Resolve "manager" → check work relationships]
       
       What time was the call, roughly?

USER: Around 3pm, maybe 30 minutes

AGENT: [Internal: Create work event with interaction_mode=virtual_audio]
       
       Added:
       • 📞 Call with [manager name] at 3pm (30 min)
       
       Anything else?
```

---

## File Structure

```
agent-orchestrator/
├── config.py              # MCP servers, LLM configs
├── mcp_bridge.py          # Dynamic tool discovery & routing
├── llm_clients.py         # Anthropic/OpenAI/Ollama adapters
├── conversation.py        # NEW: ConversationManager, SessionState
├── skeleton.py            # NEW: TimelineSkeletonBuilder
├── skills.py              # NEW: SkillsLoader
├── agent.py               # UPDATED: Agent core with conversation + skeleton
├── cli.py                 # CLI interface
├── server.py              # FUTURE: HTTP API for mobile
├── ARCHITECTURE.md        # This document
└── README.md              # Usage instructions
```

---

## Open Questions

1. **Distillation model** — Use same LLM or cheaper model for summarization?
2. **Session persistence** — Store sessions in DB for mobile app resume?
3. **Skeleton caching** — Cache skeleton during session, or rebuild each turn?
4. **Error recovery** — If MCP server dies mid-session, how to recover?

---

## Future Enhancements (Deferred)

1. **Bank statement parser** — Monthly CSV import for financial backfill
2. **Location tracking** — iOS app for automatic location capture
3. **Multi-device sync** — Same user from phone + desktop

---

## Next Steps

1. [ ] Validate this architecture
2. [ ] Implement `skeleton.py` (TimelineSkeletonBuilder)
3. [ ] Implement `conversation.py` (ConversationManager, SessionState)
4. [ ] Implement `skills.py` (SkillsLoader)
5. [ ] Update `agent.py` to use skeleton + conversation + skills
6. [ ] Test end-to-end with CLI
7. [ ] Add HTTP server for mobile access
