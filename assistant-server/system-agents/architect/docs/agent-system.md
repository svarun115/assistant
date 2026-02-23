# Agent System

## Two agent categories

### User agents
DB-backed. Two tables: `agent_templates` (shared) + `agent_instances` (per-user).

| | agent_templates | agent_instances |
|---|---|---|
| Purpose | Shared definition, seeded once from agents/ | Per-user copy with mutable SOUL |
| user_id | None (service-level) | Per user |
| Soul | No | Yes — grows over sessions, never reset |
| Customization | No | Yes — any file can be overridden |
| Seeded from | agents/ directory (setup only) | Copied from template on first use, or COS-created |

Current user agent templates: cos (v2), financial-advisor (v2), fitness-coach (v2)

### System agents
Filesystem-backed. Lives in system-agents/ (ships with Docker image).
Service-level: same for all users, no soul, no per-user instances.

| | System agents |
|---|---|
| Location | system-agents/{name}/ in Docker image |
| Soul | No |
| Per-user state | No |
| Access control | AGENT.md frontmatter: cos_internal, admin_direct |
| Files loaded | AGENT.md + BOOTSTRAP.md (index) + docs/ (reference) |

Current system agents: architect

## AgentLoader resolution order
```
1. agent_instances WHERE user_id=? AND agent_name=? AND is_active=TRUE → return
2. agent_templates WHERE name=? → copy to new instance → return
3. system-agents/{name}/ → enforce access rules → return from filesystem
4. None → AgentNotFoundError
```

## HEARTBEAT.md schedule format
```yaml
---
schedules:
  - name: weekly-recap            # agent_name in scheduler = "{agent_name}-{name}"
    cron: "30 2 * * 1"            # UTC cron expression
    description: "..."
    task: >                        # task prompt for spawn_background
      ...
    artifact_type: fitness_weekly  # type field in artifacts table
triggers:
  - id: low_body_battery
    condition: body_battery_below_40_for_3_consecutive_days
    message: "..."                 # what COS surfaces to user
    priority: normal               # urgent | normal | low
    action: offer_foreground_session
---
```

Schedules sync: `AgentScheduler.sync_from_heartbeats(loader, user_id)` → reads all active
instances' heartbeat_md → upserts to scheduler table.

## Agent spawning (AgentSpawner)

### Task agent (invoke_task)
```python
result = await spawner.invoke_task(user_id, skill, task, context)
# → ephemeral LangGraph thread (not tracked in ThreadManager)
# → message: "/{skill} {task}"
# → returns text to COS
# → never visible to user
```

### Background agent (spawn_background)
```python
run_id = await spawner.spawn_background(user_id, agent_name, skill, config)
# → asyncio.create_task(_run_background(...))
# → runs skill with config["task"] as prompt
# → writes artifact: write_artifact(user_id, agent_name, config["artifact_type"], result)
# → posts notification: post(user_id, agent_name, message, artifact_id=artifact_id)
# → on failure: posts urgent notification with error message
```

### Foreground agent (spawn_foreground)
```python
thread_id = await spawner.spawn_foreground(user_id, skill, title, pre_task)
# → creates ThreadManager thread (tracked, user can switch to it)
# → if no pre_task: loads agent's bootstrap_md from AgentLoader as pre_task
# → runs pre_task in background (asyncio.create_task)
# → returns thread_id immediately — user switches while pre-warm runs
```

## Creating user-defined agents (by COS)
```python
agent_name = await loader.create(
    user_id, agent_name, agent_md, tools_md, bootstrap_md, heartbeat_md,
    created_by='cos'
)
await scheduler.sync_from_heartbeats(loader, user_id)
# → new schedules from heartbeat_md are registered in scheduler table
```

## Soul management
```python
# After a foreground session ends:
await loader.append_soul(agent_name, user_id, "2026-02-22: key decision or memory...")

# User updates a file on their instance:
await loader.update_file(agent_name, user_id, "agent_md", new_content)
# → sets customized_files = ['agent_md', ...]
# → template upgrades won't overwrite customized files
```
