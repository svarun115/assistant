
# MCP Server Implementation Guide (Expanded)

**Audience:** coding agent / implementer  
**Goal:** Build one MCP server that works across **VS Code**, **Claude**, and **ChatGPT/OpenAI** with a single codebase and two transports.

---

## 1) Transport Strategy (TL;DR)

Support **exactly two** transports:

1. **stdio** — best for local development; VS Code can spawn your process and speak MCP over stdin/stdout.  
2. **Streamable HTTP** — modern single-endpoint HTTP transport for remote access by VS Code, Claude, and ChatGPT.

**Do not implement** raw WebSocket transport for MCP (non-standard).  
**Avoid** legacy “SSE-only” transport (separate endpoints).

---

## 2) The SSE Nuance (Important)

There are **two different things** that both say “SSE”:

- **Legacy SSE transport (avoid):** historically, MCP servers exposed one or more dedicated SSE endpoints (e.g., `/events`) and clients always consumed those. That shape is deprecated.
- **SSE *inside* Streamable HTTP (required):** the modern **Streamable HTTP** transport uses a **single endpoint** (e.g., `/mcp`). When the server needs to stream a response, it **switches the HTTP response** to `Content-Type: text/event-stream` and emits SSE **within the same response**.

### What this means for implementation

- **Client → Server:** You receive **JSON-RPC** messages over **HTTP POST** to `/mcp` (single endpoint).
- **Server → Client (responses):** Either
  - **Non-streaming:** Respond with `Content-Type: application/json` and a **single JSON-RPC response** object; or
  - **Streaming:** Respond with `Content-Type: text/event-stream` and send **SSE frames**. Each SSE event contains a **full JSON-RPC message** in the `data:` line(s). End each event with a **blank line**.
- **Optional background stream:** A `GET /mcp` can open an **optional persistent SSE stream** for server-initiated notifications.

**You are not implementing the legacy SSE transport** — you’re implementing **Streamable HTTP** that *uses* SSE only when streaming in a response.

---

## 3) Endpoint & Framing Rules (Streamable HTTP)

- **Single endpoint**: e.g., `/mcp`. Do **not** split into `/jsonrpc`, `/events`, `/ws`, etc.
- **POST /mcp**: client sends one JSON-RPC message per POST body.
- **Response to POST**:
  - If the client sent a **request** (expects a reply):  
    - non-streaming → `Content-Type: application/json` with one JSON object (a JSON-RPC response)  
    - streaming → `Content-Type: text/event-stream` and emit valid SSE frames
  - If the client sent a **notification** (no reply expected): return **`202 Accepted`** with an empty body.
- **SSE framing** (when streaming):
  - Each event = one or more `data: <json>` lines (if the JSON is long, split across multiple `data:` lines).  
  - **Blank line** terminates the event.  
  - Do **not** send arbitrary newline-delimited JSON; it must be valid SSE framing.
- **Headers**:
  - Accept both: `Accept: application/json, text/event-stream`
  - Use/accept `MCP-Protocol-Version` header; reject unsupported versions with 400.
- **Security**:
  - Validate/allowlist `Origin` in production.  
  - Use HTTPS in production and require auth (bearer/OAuth).

---

## 4) stdio Transport

- The server reads JSON-RPC from **stdin** and writes to **stdout**.
- Ideal for local development because IDEs (like VS Code) can spawn the process directly.

**VS Code config (stdio):**
```json
{
  "servers": {
    "my-local-stdio": {
      "type": "stdio",
      "command": "my-mcp-server",
      "args": ["--stdio"]
    }
  }
}
```

**Start command (example):**
```bash
my-mcp-server --stdio
```

---

## 5) Streamable HTTP Transport

- Expose **one** route: `/mcp`
  - **POST** handles client → server JSON-RPC
  - **GET** (optional) opens a background SSE stream

**VS Code config (http):**
```json
{
  "servers": {
    "my-local-http": {
      "type": "http",
      "url": "http://127.0.0.1:3333/mcp"
    }
  }
}
```

**Start command (example):**
```bash
my-mcp-server --http --port 3333  # /mcp is the single endpoint
```

**Local curl smoke tests:**
```bash
# Optional: background SSE stream (should stay open)
curl -N -H "Accept: text/event-stream" http://127.0.0.1:3333/mcp

# Send a JSON-RPC "initialize" over POST (transport-only test)
curl -X POST -H "Content-Type: application/json"   -d '{"jsonrpc":"2.0","id":"1","method":"initialize","params":{}}'   http://127.0.0.1:3333/mcp
```

---

## 6) How Each Client Connects

### VS Code (Copilot Chat / MCP-enabled)
- **Local dev**: prefers **stdio**. VS Code spawns your process (see stdio config above).
- **Remote**: supports **Streamable HTTP** directly (`type: "http"`). It may fall back to legacy SSE if offered, but you don’t need to support that if Streamable HTTP is correct.
- **Auth**: When remote, protect your server (TLS + auth). VS Code can participate in OAuth flows depending on host setup.

### Claude
- The Claude MCP connector is designed for **remote servers**. Point it at your **Streamable HTTP** URL (e.g., `https://your.host/mcp`).
- Focus on the Streamable HTTP contract; Claude does not need the stdio variant (that’s mostly for local IDEs).

### ChatGPT / OpenAI (Agents / Responses API + MCP)
- Integrations expect **remote MCP** via **Streamable HTTP**.
- If it works with VS Code’s `type: "http"` against your `/mcp`, you’re aligned. (Legacy SSE support is for back-compat only; not required if Streamable HTTP is correct.)

> **Practical rule of thumb:**  
> - For **local testing** in VS Code, use `stdio`.  
> - For **everything remote** (VS Code, Claude, ChatGPT), use **Streamable HTTP** at `/mcp` over **HTTPS** with **auth**.

---

## 7) Minimal Response Patterns

### Non-streaming JSON reply
```
POST /mcp
Content-Type: application/json
Accept: application/json, text/event-stream

{ "jsonrpc": "2.0", "id": "42", "method": "tools/call", "params": {...} }

HTTP/1.1 200 OK
Content-Type: application/json

{ "jsonrpc": "2.0", "id": "42", "result": {...} }
```

### Streaming reply (SSE-in-HTTP)
```
POST /mcp
Content-Type: application/json
Accept: application/json, text/event-stream

{ "jsonrpc": "2.0", "id": "42", "method": "tools/call", "params": {...} }

HTTP/1.1 200 OK
Content-Type: text/event-stream

data: { "jsonrpc":"2.0","method":"tool/output","params":{"chunk":"hello "} }

data: { "jsonrpc":"2.0","method":"tool/output","params":{"chunk":"world"} }

data: { "jsonrpc":"2.0","id":"42","result":{"status":"done"} }
```

> Notes: Each `data:` line can be wrapped. **Blank line** terminates an event. Continue emitting events until the final result event.

### Notification (no response body)
```
POST /mcp
Content-Type: application/json

{ "jsonrpc": "2.0", "method": "ping" }   // notification (no id)

HTTP/1.1 202 Accepted
```

---

## 8) Project Structure (suggested)

```
server/
  core/
    mcp_handlers.py          # Shared business logic (tools/resources/prompts)
  transport/
    stdio.py                 # Reads/writes JSON-RPC via stdin/stdout
    http.py                  # Single-endpoint /mcp, POST+GET, SSE streaming
  utils/
    sse.py                   # Helpers for SSE framing
    jsonrpc.py               # Validation, id->pending map, notifications
main.py                      # CLI entrypoint (--stdio / --http)
```

**CLI examples:**
```bash
python main.py --stdio
python main.py --http --port 3333 --host 127.0.0.1
```

---

## 9) State & Sessions

- MCP sessions can be **stateless** or **stateful**.
- If you keep state per client, consider:
  - A session identifier (e.g., `Mcp-Session-Id` header or a token in auth claims).
  - Sticky routing at your reverse proxy, or a session store.
- Avoid storing sensitive state server-side without auth.

---

## 10) Production Checklist

- **HTTPS** (TLS) via reverse proxy (nginx/Caddy/Envoy).  
- **Auth** (bearer tokens or OAuth).  
- **Origin** allowlist.  
- **Rate limits** and request size caps.  
- **Logging** (but avoid logging secrets/tool inputs by default).  
- **Timeouts** for long streams; graceful cleanup.  
- **Health endpoint** (e.g., `/healthz`) separate from `/mcp`.  
- **Backpressure** on streaming responses to avoid memory blow-ups.

---

## 11) Quick Troubleshooting

- **VS Code won’t connect (HTTP):** Check that you use **one endpoint** and reply either JSON or SSE; confirm 202 on notifications; confirm `MCP-Protocol-Version` handling.  
- **No streaming visible:** Ensure you set `Content-Type: text/event-stream` and emit valid SSE with blank-line terminators.  
- **Random disconnects:** Look for proxies stripping `text/event-stream` or buffering; disable response buffering/enable streaming.  
- **CORS/origin errors:** During local dev, allow `http://localhost` and `http://127.0.0.1`; in prod, strict allowlist.  
- **WebSocket attempts:** Remove any WS endpoints from your MCP config; clients won’t use them.

---

## 12) Final Recap

- Implement **stdio** and **Streamable HTTP**.  
- Streamable HTTP uses **SSE only when streaming the response** — not as a separate transport.  
- Test locally in VS Code with both `type: "stdio"` and `type: "http"`.  
- Deploy one HTTPS `/mcp` endpoint with auth for Claude and ChatGPT (and VS Code remote).

