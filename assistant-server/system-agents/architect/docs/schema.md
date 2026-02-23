# Database Schema — assistant_system

## threads
| Column | Type | Notes |
|---|---|---|
| thread_id, user_id | TEXT | PK composite |
| title | TEXT | |
| created_at, last_updated | TIMESTAMPTZ | |
| message_count | INT | |
| total_input_tokens, total_output_tokens | BIGINT | |
| mode | TEXT | default 'chat' |
| target_date | DATE | |
| model_provider, model_name | TEXT | |
| is_deleted | BOOLEAN | soft delete |
| emoji | TEXT | |

RLS: `user_id = current_setting('app.user_id', true)`

## scheduler
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | TEXT | |
| agent_name | TEXT | unique with user_id (active) |
| skill | TEXT | |
| cron | TEXT | UTC expression |
| next_run, last_run | TIMESTAMPTZ | |
| is_active | BOOLEAN | |
| config | JSONB | `{task, artifact_type, description}` |

Unique constraint: `(user_id, agent_name) WHERE is_active=TRUE`

## notifications
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | TEXT | |
| from_agent | TEXT | |
| to_thread_id | TEXT | NULL = any active COS thread |
| message | TEXT | |
| priority | TEXT | urgent / normal / low |
| artifact_id | UUID | FK to artifacts |
| created_at, read_at | TIMESTAMPTZ | NULL read_at = unread |

## artifacts
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | TEXT | |
| agent_id | TEXT | producing agent |
| type | TEXT | daily_plan, email_digest, portfolio_weekly, fitness_weekly, retro, expense_reminder |
| content | TEXT | markdown/JSON body |
| metadata | JSONB | `{run_id, config}` |
| created_at | TIMESTAMPTZ | |
| is_deleted | BOOLEAN | |

## agent_templates
| Column | Type | Notes |
|---|---|---|
| name | TEXT PK | |
| description | TEXT | |
| source | TEXT | pre_built / imported |
| agent_md | TEXT | AGENT.md content |
| tools_md | TEXT | TOOLS.md content |
| bootstrap_md | TEXT | BOOTSTRAP.md content |
| heartbeat_md | TEXT | HEARTBEAT.md content (includes schedule YAML) |
| content_hash | TEXT | SHA-256 for change detection |
| version | INT | bumped on content change |

No RLS. Service-level. Current: cos v2, financial-advisor v2, fitness-coach v2, architect v1.

## agent_instances
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | TEXT | |
| agent_name | TEXT | unique with user_id |
| template_name | TEXT | NULL = user-defined |
| source | TEXT | from_template / user_defined / imported |
| agent_md, tools_md, bootstrap_md, heartbeat_md | TEXT | possibly user-customized |
| soul_md | TEXT | mutable memory, never reset by upgrades |
| customized_files | TEXT[] | tracks what user changed |
| template_version | INT | at creation time |
| upgrade_available | BOOLEAN | set when template updates |
| is_active | BOOLEAN | |
| created_by | TEXT | system / cos / user / seeder |

RLS: user_id isolation.
Resolution: instances (user row) → templates (copy on first use) → error.

## api_keys
| Column | Type | Notes |
|---|---|---|
| key_hash | TEXT PK | SHA-256 of raw key |
| user_id | TEXT | |
| profile_name | TEXT | default 'personal' |
| label | TEXT | e.g. "varun's laptop" |
| allow_operator_llm | BOOLEAN | admin grants operator LLM key fallback |
| last_used, created_at | TIMESTAMPTZ | |
| is_revoked | BOOLEAN | |

No RLS. Read before user_id is known.

## user_credentials
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id, service | TEXT | unique pair |
| token_data | BYTEA | AES-256-GCM encrypted JSON |
| encryption_key_id | TEXT | default 'v1' for rotation |
| expires_at | TIMESTAMPTZ | NULL = non-expiring |
| scopes | TEXT[] | OAuth scopes |

Services: google, garmin, splitwise, llm_anthropic, llm_openai

BYOK token shapes:
- llm_anthropic: `{"api_key": "sk-ant-...", "preferred_model": "claude-sonnet-4-6"}`
- llm_openai: `{"api_key": "sk-...", "preferred_model": "gpt-5-nano"}`
