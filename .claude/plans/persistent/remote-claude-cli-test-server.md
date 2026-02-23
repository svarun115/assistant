# Plan: Minimal Test Server for Remote Claude CLI Access

## Context

You want to quickly test using Claude CLI (via agency) remotely from your phone before building out the full agent-gateway architecture. This will validate that:
1. Agency CLI can be invoked programmatically
2. Response capture works
3. Network access from phone works
4. Latency is acceptable for remote use

You have an agent-gateway project with comprehensive documentation but no implementation yet. This minimal test server will serve as the foundation that evolves into the full gateway.

## Protocol Decision: HTTP REST

**Chosen: HTTP REST over JSON-RPC**

Rationale:
- Multiple free REST client apps available for phones (HTTPBot, Rest API Client)
- Simplest to implement and test (single endpoint, standard request/response)
- Aligns with your documented architecture (HTTP API + Channel Adapters)
- Easy to test with curl from any device
- Evolution path: minimal changes needed to add Telegram/WhatsApp adapters later

JSON-RPC would add complexity without benefit for a single-endpoint use case.

## Implementation Approach

### Architecture

```
Phone (HTTPBot app)
      |
      | POST /chat
      | { "message": "what is 2+2" }
      | Header: Authorization: Bearer <api-key>
      v
+------------------+
|  Fastify Server  |
|  Port 3000       |
|  (test-server.js)|
+------------------+
      |
      | 1. Validate API key (Bearer token)
      | 2. Spawn subprocess
      v
+------------------+
|  agency claude   |
|  -p "..." -s     |
+------------------+
      |
      | stdout capture (2min timeout)
      v
{ "response": "...", "timestamp": "...", "elapsed_ms": 1234 }
      |
      v
    Phone
```

### Critical Files

1. **[test-server.js](C:\Users\vasashid\Projects\agent-gateway\test-server.js)** - Standalone minimal server (~80 lines)
   - Single `/chat` endpoint
   - Bearer token authentication
   - Agency CLI wrapper with timeout handling
   - Error handling and logging

2. **[.env.test](C:\Users\vasashid\Projects\agent-gateway\.env.test)** - API key configuration
   - Single API_KEY variable (32-char random string)

### Implementation Details

**Endpoint: POST /chat**

Request format:
```json
{
  "message": "what is the weather",
  "engine": "claude"  // optional, default: claude
}
```

Response format:
```json
{
  "response": "...",
  "timestamp": "2026-02-18T...",
  "engine": "claude",
  "elapsed_ms": 1234
}
```

**Security: Bearer Token**
- Generate random 32-char API key
- Include in Authorization header: `Bearer <api-key>`
- Sufficient for local network or Tailscale access
- Single-user validation (matches your gateway design)

**Agency CLI Invocation**

⚠️ **Critical: Nested Session Constraint**

Agency CLI cannot run inside a Claude Code session. If running the test server from a Claude Code terminal, you must unset the `CLAUDECODE` environment variable:

```javascript
spawn('agency', [engine, '-p', message, '-s'], {
  shell: true,
  timeout: 120000,  // 2 minute timeout
  env: {
    ...process.env,
    CLAUDECODE: undefined  // Allow nested sessions
  }
})
```

**Recommended:** Run the test server from a regular terminal (not from within Claude Code) to avoid this issue entirely.

**Error Handling**
- Authentication failures: 401 with code `AUTH_FAILED`
- Invalid requests: 400 with code `INVALID_REQUEST`
- Timeouts: 504 with code `TIMEOUT`
- Agency errors: 500 with code `AGENCY_ERROR`

### Dependencies

Minimal additions to existing package.json:
- `fastify` - Lightweight HTTP server
- `dotenv` - Environment variable management

Already have: `child_process` (Node.js built-in)

## Implementation Steps

### 1. Create test-server.js (15 minutes)
Create standalone server file with:
- Fastify server setup
- Bearer token authentication middleware
- `/health` endpoint (no auth required)
- `/chat` endpoint (auth required)
- Agency CLI wrapper function with timeout handling
- Error handling for all failure modes

### 2. Create .env.test (1 minute)
Generate random API key:
```bash
echo "API_KEY=$(openssl rand -hex 16)" > .env.test
```

### 3. Test locally with curl (5 minutes)

⚠️ **Important:** Run from a regular terminal, not from within Claude Code session.

```bash
# Start server (from regular terminal, not Claude Code)
node test-server.js

# Test health check
curl http://localhost:3000/health

# Test chat endpoint
curl -X POST http://localhost:3000/chat \
  -H "Authorization: Bearer <your-api-key>" \
  -H "Content-Type: application/json" \
  -d '{"message": "what is 2+2"}'
```

### 4. Expose via Tailscale (5 minutes)
```bash
# Get Tailscale IP
tailscale ip -4
# Example: 100.x.y.z

# Access from phone: http://100.x.y.z:3000/chat
```

Alternative: Use local network IP (192.168.1.x) if on same WiFi.

### 5. Test from phone (10 minutes)
Using HTTPBot app (or similar REST client):
1. Install HTTPBot from App Store
2. Create POST request to `http://100.x.y.z:3000/chat`
3. Add headers:
   - `Authorization`: `Bearer <your-api-key>`
   - `Content-Type`: `application/json`
4. Add JSON body: `{"message": "hello from phone"}`
5. Send and verify response

## Evolution Path to Full Gateway

This test server establishes the foundation for the full gateway:

**What stays the same:**
- Core `invokeAgency()` function (extract to `src/core/agency.ts`)
- Authentication pattern (Bearer token → Telegram user ID validation)
- Error handling structure
- Timeout handling (2 minutes)

**What gets added:**
1. **Context management** (`src/core/context.ts`):
   - SQLite database for conversation history
   - Include last N messages in prompt

2. **Skills system** (`src/core/skills.ts`):
   - Load markdown skills from `~/.agent-gateway/skills/`
   - Match triggers (`/expense`, `/journal`, etc.)
   - Inject skill instructions into prompts

3. **Telegram adapter** (`src/channels/telegram.ts`):
   - Replace `/chat` endpoint with Telegram webhook
   - Use grammY library for bot handling
   - User ID validation instead of Bearer token

4. **Configuration** (`src/config.ts`):
   - Move from `.env.test` to `~/.agent-gateway/config.yaml`
   - Support multiple engines, models, MCP servers

**Migration path:** test-server.js (80 lines) → src/ directory structure → Full gateway architecture

## Verification Steps

**Pre-deployment checklist:**
- [ ] Server starts without errors
- [ ] `/health` endpoint responds with `{"status":"ok"}`
- [ ] curl test from localhost succeeds
- [ ] Authentication rejects requests without valid Bearer token
- [ ] Agency CLI invocation returns expected response
- [ ] Response includes all expected fields (response, timestamp, engine, elapsed_ms)
- [ ] Timeout handling works (test with artificially long request)
- [ ] Error responses include proper error codes

**Phone testing checklist:**
- [ ] Tailscale IP accessible from phone
- [ ] HTTPBot can send request successfully
- [ ] Response displays correctly in app
- [ ] Latency is acceptable (<10s for simple queries)
- [ ] Works over cellular data (via Tailscale)
- [ ] Works over local WiFi (if using local network)

**Success criteria:**
- Can send a message from phone and receive Claude's response
- Response time is under 10 seconds for simple queries
- Server remains stable across multiple requests
- Error handling works gracefully

## Estimated Timeline

| Phase | Time | Description |
|-------|------|-------------|
| Write test-server.js | 15 min | Complete implementation |
| Create .env.test | 1 min | Generate API key |
| Test with curl | 5 min | Verify locally |
| Expose via Tailscale | 5 min | Get IP, test accessibility |
| Install HTTPBot | 5 min | Download and configure |
| Test from phone | 10 min | Send requests, verify |
| **Total** | **~40 min** | **End-to-end working demo** |

## Open Questions

None - the minimal design is straightforward and all requirements are clear. The test server will validate the core concept before investing in the full gateway architecture.

## Next Steps After Validation

Once the minimal test proves successful:
1. Migrate to TypeScript (`test-server.js` → `src/index.ts`)
2. Add SQLite context management
3. Implement skills system
4. Add Telegram adapter (replace HTTP endpoint with Telegram webhook)
5. Implement full configuration system
6. Add remaining channel adapters (WhatsApp, Teams)

This incremental approach minimizes risk and allows you to validate each layer before adding the next.
