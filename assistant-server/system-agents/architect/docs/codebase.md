# Codebase Reference

```
journal-processor/agent-orchestrator/
  web_server.py         FastAPI app. Startup: profile → auth_pool → CredentialStore →
                        BridgeManager → AgentLoader → NotificationQueue → AgentSpawner →
                        AgentScheduler → ThreadManager → LangGraph graph.
  profile.py            AssistantProfile + build_personal_profile(). All config from env.
  config.py             MCPServerConfig, LLMConfig, LLMProvider, MCPTransport enums.
  mcp_bridge.py         MCPToolBridge. _connect_http() passes config.headers to
                        streamablehttp_client. to_filtered_tools(allowed_servers).
  bridge_manager.py     BridgeManager. Per-user bridge cache. SERVER_CREDENTIAL_MAP:
                        garmin→X-Garmin-Token, google-workspace→Authorization,
                        splitwise→X-Splitwise-Key.
  credential_store.py   AES-256-GCM. get/put/delete/list_services on user_credentials.
                        Lazy key rotation via encryption_key_id.
  agent_loader.py       AgentLoader.resolve(name, user_id) → AgentDefinition.
                        AgentSeeder.sync(): agents/ dir → agent_templates (setup only).
                        AgentDefinition.get_system_prompt() = agent_md + soul.
                        .allowed_servers from tools_md YAML. .schedules/.triggers from heartbeat_md.
  agent_spawner.py      invoke_task(skill, task) → ephemeral thread → text.
                        spawn_background(agent_name, skill, config) → asyncio.create_task.
                        spawn_foreground(skill, pre_task) → ThreadManager thread → thread_id.
                        spawn_foreground reads BOOTSTRAP.md from AgentLoader as pre_task.
  scheduler.py          Polls scheduler table every 60s. sync_from_heartbeats(loader, user_id)
                        syncs HEARTBEAT schedule declarations → scheduler table.
  notification_queue.py NotificationQueue: register/unregister WS, post, get_unread, mark_read.
                        ArtifactStore: write_artifact, get_artifact, list_artifacts.
  skills.py             SkillsLoader for task skills (~/.claude/skills/).
                        SKILL_MAP, SKILL_SUPPORT_FILES, SKILL_ALLOWED_SERVERS.
  graph/graph.py        JournalGraph. create_journal_graph_postgres(pg_dsn).
                        _get_config(thread_id, mcp_bridge=None) — per-call bridge override.
  graph/nodes.py        update_history, skill_router, detect_context, build_skeleton,
                        prepare_llm_context, call_llm, execute_tools, store_turn.
  graph/thread_manager.py SQLite ThreadManager (PG migration pending).
  agents/               Agent definition files (seeding source — not in Docker image)
    cos/                Active, always-on. DB-backed instance per user.
    architect/          Service-level system agent. Reads docs from filesystem.
    financial-advisor/  Dormant template, user activates during setup.
    fitness-coach/      Dormant template, user activates during setup.
  migrations/           Run once during deployment setup (never at startup).
```
