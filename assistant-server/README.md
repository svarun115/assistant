# Journal Agent Orchestrator

A parameterized agent orchestrator that bridges MCP servers with various LLM providers.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                      CLI / API                       │
│              (cli.py / future: api.py)              │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│                  JournalAgent                        │
│                   (agent.py)                         │
│  • Loads skills/system prompt                        │
│  • Manages conversation state                        │
│  • Implements agentic loop                           │
└──────────┬──────────────────────────┬───────────────┘
           │                          │
┌──────────▼──────────┐    ┌──────────▼──────────┐
│    LLM Clients      │    │    MCP Tool Bridge   │
│  (llm_clients.py)   │    │   (mcp_bridge.py)    │
│                     │    │                      │
│  • Claude           │    │  • Dynamic discovery │
│  • OpenAI           │    │  • Schema conversion │
│  • Ollama           │    │  • Tool routing      │
└─────────────────────┘    └──────────┬───────────┘
                                      │
                      ┌───────┬───────┼───────┬───────┐
                      │       │       │       │       │
                      ▼       ▼       ▼       ▼       ▼
                 [Journal] [Garmin] [Gmail] [Places] [GitHub]
                    MCP      MCP     MCP     MCP      MCP
```

## Key Design Decisions

### Dynamic Tool Discovery

The `MCPToolBridge` connects to MCP servers and discovers tools at runtime:
- No hardcoded tool definitions in agent code
- Add/remove tools on MCP server → agent adapts automatically
- Tool schemas converted to LLM-specific formats on-the-fly

### Pluggable LLM Providers

The `BaseLLMClient` abstraction allows swapping LLMs:
- Same agent code works with Claude, OpenAI, or Ollama
- Each provider handles its own API format
- Easy to add new providers

### Future-Proof

When Anthropic (or others) ship native LLM+MCP integration:
- Keep `JournalAgent` and `cli.py`
- Replace `MCPToolBridge` with native solution
- Zero changes to skills or MCP servers

## Quick Start

### 1. Install Dependencies

```bash
cd agent-orchestrator
pip install -r requirements.txt
```

### 2. Set Environment Variables

```bash
# Required for Claude
export ANTHROPIC_API_KEY="sk-ant-..."

# Required for OpenAI
export OPENAI_API_KEY="sk-..."

# For MCP servers
export JOURNAL_DATABASE_URL="postgresql://..."
export GOOGLE_PLACES_API_KEY="..."
export GITHUB_TOKEN="..."
```

### 3. Configure MCP Servers

Edit `config.py` to set the correct paths and commands for your MCP servers.

### 4. Run

```bash
# With Claude (default)
python cli.py

# With OpenAI
python cli.py --llm openai

# With local Ollama
python cli.py --llm ollama --model llama3.2

# List available MCP servers
python cli.py --list-servers

# Use specific servers only
python cli.py --servers journal-db,garmin
```

## CLI Commands

Once running, use these commands:

| Command | Description |
|---------|-------------|
| `/tools` | List all available MCP tools |
| `/clear` | Clear conversation history |
| `/history` | Show conversation history |
| `/quit` | Exit the agent |

## Files

| File | Purpose |
|------|---------|
| `config.py` | MCP server configs, LLM configs, defaults |
| `mcp_bridge.py` | Dynamic MCP tool discovery and routing |
| `llm_clients.py` | Unified LLM provider abstraction |
| `agent.py` | Main agent orchestrator |
| `cli.py` | Command-line interface |

## Extending

### Add a New LLM Provider

1. Create a new class in `llm_clients.py` extending `BaseLLMClient`
2. Implement `initialize()`, `chat()`, and `format_tool_result()`
3. Add to `LLMProvider` enum and `create_llm_client()` factory

### Add a New MCP Server

1. Add a `MCPServerConfig` entry in `config.py`
2. That's it - tools are discovered automatically

## Roadmap

- [ ] Web API (FastAPI) for mobile app backend
- [ ] WebSocket support for streaming responses
- [ ] Conversation persistence (SQLite/Redis)
- [ ] Multi-user authentication
- [ ] Server-side MCP (when available)
