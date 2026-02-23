# Security Model

## Authentication flow
```
Request → APIKeyMiddleware
  → SHA-256(incoming key) → lookup api_keys table
  → Returns: user_id, profile_name, allow_operator_llm
  → Attaches to request.state
  → Local dev fallback: if no SYSTEM_DB_URL, string compare against ASSISTANT_API_KEY env
```

## Roles (profile_name in api_keys)
| profile_name | Access |
|---|---|
| personal | Regular user. Accesses system only through COS. |
| admin | Operator/superuser. Can invoke system agents directly, manage api_keys, view all users. |
| cos_internal | Internal trust level used when COS invokes system agents as task agents. |

## BYOK resolution (get_or_create_graph)
```
1. CredentialStore.get(user_id, "llm_anthropic" or "llm_openai")
2. If found → use user's key
3. If not found AND allow_operator_llm=TRUE → use operator env key
4. If not found AND allow_operator_llm=FALSE → HTTP 403
```
`allow_operator_llm` is set by admin in api_keys table. Default FALSE for new users.

## Credential encryption
- Algorithm: AES-256-GCM (Python cryptography library)
- Format: nonce (12 bytes) + ciphertext, stored as BYTEA
- Key: `CREDENTIALS_ENCRYPTION_KEY` env var (64 hex chars = 32 bytes)
- Rotation: `encryption_key_id` tracks key version; lazy re-encryption on read

## Multi-user isolation
- Every user-owned table has `user_id` column
- Row-Level Security on all user tables: `user_id = current_setting('app.user_id', true)`
- `api_keys` and `agent_templates` have no RLS (read before user_id is known)

## BridgeManager — per-user credentials
```python
SERVER_CREDENTIAL_MAP = {
    "garmin":           ("garmin",    "X-Garmin-Token"),
    "google-workspace": ("google",    "Authorization"),  # Bearer {access_token}
    "splitwise":        ("splitwise", "X-Splitwise-Key"),
}
# journal-db and google-places use operator env credentials (no per-user override yet)
```
MCP server-side per-user header handling: Phase 2+ work. Headers are injected but currently ignored.

## System agent access control
AGENT.md frontmatter `access` list:
- `cos_internal`: COS can invoke as internal task (any user's COS)
- `admin_direct`: Only profile_name='admin' callers can invoke directly

Regular users cannot invoke system agents. COS never relays raw system agent responses to users.
