#!/usr/bin/env python3
"""
Journal Agent CLI - Interactive command-line interface using LangGraph.

Usage:
    python cli.py                      # Use default (Claude)
    python cli.py --llm openai         # Use OpenAI
    python cli.py --llm ollama         # Use local Ollama
    python cli.py --list-servers       # Show available MCP servers
    python cli.py --servers journal-db,garmin  # Use specific servers
"""

import argparse
import asyncio
import logging
import sys
import uuid
from typing import Optional

# Fix Windows console encoding for Unicode
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from config import (
    LLMProvider,
    MCPServerConfig,
    DEFAULT_MCP_SERVERS,
    get_default_llm_config,
    get_enabled_mcp_servers,
)
from graph import create_journal_graph, ThreadManager, JournalGraph
from llm_clients import create_llm_client
from mcp_bridge import MCPToolBridge
from skeleton import TimelineSkeletonBuilder
from skills import SkillsLoader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Journal Agent - AI-powered personal journaling assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python cli.py                          # Start with Claude (default)
    python cli.py --llm openai             # Use OpenAI GPT-4
    python cli.py --llm ollama             # Use local Llama
    python cli.py --model claude-3-opus    # Specify model
    python cli.py --servers journal-db     # Use only journal-db server
    python cli.py --list-servers           # Show available servers
    python cli.py --debug                  # Enable debug logging
        """
    )
    
    parser.add_argument(
        "--llm",
        type=str,
        choices=["claude", "openai", "ollama"],
        default="claude",
        help="LLM provider to use (default: claude)"
    )
    
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Specific model to use (overrides default for provider)"
    )
    
    parser.add_argument(
        "--servers",
        type=str,
        default=None,
        help="Comma-separated list of MCP servers to enable (default: all enabled)"
    )
    
    parser.add_argument(
        "--list-servers",
        action="store_true",
        help="List available MCP servers and exit"
    )
    
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="Connect and list all available tools, then exit"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    return parser.parse_args()


def list_servers() -> None:
    """Print available MCP servers."""
    print("\nAvailable MCP Servers:")
    print("-" * 70)
    for server in DEFAULT_MCP_SERVERS:
        status = "✓ enabled" if server.enabled else "✗ disabled"
        transport = server.transport.value.upper()
        print(f"  {server.name:20} [{transport:6}] [{status}]")
        if server.transport.value == "stdio":
            print(f"    Command: {server.command} {' '.join(server.args)}")
        else:
            print(f"    URL: {server.url}")
        print(f"    {server.description}")
    print()


def get_selected_servers(server_names: Optional[str]) -> list[MCPServerConfig]:
    """Get MCP servers based on selection."""
    if not server_names:
        return get_enabled_mcp_servers()
    
    names = [n.strip() for n in server_names.split(",")]
    selected = []
    
    for server in DEFAULT_MCP_SERVERS:
        if server.name in names:
            server.enabled = True
            selected.append(server)
    
    if not selected:
        print(f"Warning: No matching servers found for: {server_names}")
        print("Use --list-servers to see available servers")
        sys.exit(1)
    
    return selected


async def list_tools(servers: list[MCPServerConfig]) -> None:
    """Connect to servers and list available tools."""
    print("\nConnecting to MCP servers...")
    
    async with MCPToolBridge() as bridge:
        await bridge.connect(servers)
        print(bridge.get_tools_summary())


class CLIAgent:
    """Wrapper around LangGraph for CLI usage."""
    
    def __init__(self, llm_config, servers: list[MCPServerConfig]):
        self.llm_config = llm_config
        self.servers = servers
        self.graph: Optional[JournalGraph] = None
        self.thread_manager: Optional[ThreadManager] = None
        self.mcp_bridge: Optional[MCPToolBridge] = None
        self.thread_id: Optional[str] = None
    
    async def initialize(self):
        """Initialize the agent."""
        # Create MCP bridge
        self.mcp_bridge = MCPToolBridge()
        await self.mcp_bridge.__aenter__()
        await self.mcp_bridge.connect(self.servers)
        tool_count = len(self.mcp_bridge.tool_names)
        logger.info(f"MCP bridge ready with {tool_count} tools")
        
        # Create supporting components
        llm_client = create_llm_client(self.llm_config)
        await llm_client.initialize()
        skeleton_builder = TimelineSkeletonBuilder(self.mcp_bridge)
        skills_loader = SkillsLoader()
        
        # Create graph
        self.graph = create_journal_graph(db_path="journal_cli.db")
        self.graph.configure(
            mcp_bridge=self.mcp_bridge,
            llm_client=llm_client,
            skeleton_builder=skeleton_builder,
            skills_loader=skills_loader,
        )
        
        # Create thread manager and initial thread
        self.thread_manager = ThreadManager("journal_cli_threads.db")
        self.thread_id = self.thread_manager.create_thread("CLI Session")
        
        logger.info(f"Agent initialized with {self.llm_config.provider.value}/{self.llm_config.model}")
    
    async def shutdown(self):
        """Clean up resources."""
        if self.mcp_bridge:
            await self.mcp_bridge.__aexit__(None, None, None)
    
    async def chat(self, message: str) -> str:
        """Process a message and return response."""
        if not self.graph or not self.thread_id:
            raise RuntimeError("Agent not initialized")
        
        response = await self.graph.chat(message, self.thread_id)
        
        # Sync thread metadata
        state = self.graph.get_state(self.thread_id)
        if state and self.thread_manager:
            self.thread_manager.sync_from_state(self.thread_id, state)
        
        return response
    
    def get_session_state(self) -> dict:
        """Get current session state."""
        if not self.graph or not self.thread_id:
            return {"mode": "idle", "target_date": None, "turn_count": 0}
        
        state = self.graph.get_state(self.thread_id)
        if not state:
            return {"mode": "idle", "target_date": None, "turn_count": 0}
        
        return {
            "mode": state.get("mode", "idle"),
            "target_date": state.get("target_date"),
            "turn_count": state.get("turn_count", 0),
            "has_skeleton": state.get("skeleton") is not None,
            "pending_entities": len(state.get("pending_entities", [])),
            "pending_events": len(state.get("pending_events", [])),
            "total_tokens": state.get("total_input_tokens", 0) + state.get("total_output_tokens", 0),
        }
    
    def get_skeleton_summary(self) -> Optional[str]:
        """Get skeleton summary if available."""
        if not self.graph or not self.thread_id:
            return None
        
        state = self.graph.get_state(self.thread_id)
        if state and state.get("skeleton"):
            return state["skeleton"].get("summary", "")
        return None
    
    def get_available_tools(self) -> list[str]:
        """Get list of available tools."""
        if self.mcp_bridge:
            return self.mcp_bridge.tool_names
        return []
    
    def get_tools_summary(self) -> str:
        """Get human-readable tools summary."""
        if self.mcp_bridge:
            return self.mcp_bridge.get_tools_summary()
        return "No tools available"
    
    def clear_conversation(self):
        """Start a new conversation thread."""
        if self.thread_manager:
            self.thread_id = self.thread_manager.create_thread("CLI Session")
    
    def get_conversation_history(self) -> list[dict]:
        """Get conversation history."""
        if not self.graph or not self.thread_id:
            return []
        
        from langchain_core.messages import HumanMessage, AIMessage
        
        messages = self.graph.get_messages(self.thread_id)
        history = []
        
        for msg in messages:
            if isinstance(msg, HumanMessage):
                history.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                entry = {"role": "assistant", "content": msg.content}
                if msg.tool_calls:
                    entry["tool_calls"] = [
                        {"name": tc["name"], "arguments": tc.get("args", {})}
                        for tc in msg.tool_calls
                    ]
                history.append(entry)
        
        return history


async def run_interactive(agent: CLIAgent) -> None:
    """Run interactive chat loop."""
    print("\n" + "=" * 60)
    print("Journal Agent - Interactive Mode (LangGraph)")
    print("=" * 60)
    print(f"LLM: {agent.llm_config.provider.value} ({agent.llm_config.model})")
    print(f"Tools: {len(agent.get_available_tools())} available")
    print("-" * 60)
    print("Commands:")
    print("  /tools          - List available tools")
    print("  /clear          - Clear conversation history")
    print("  /history        - Show conversation history")
    print("  /history full   - Show history with tool call details")
    print("  /session        - Show current session state")
    print("  /skeleton       - Show timeline skeleton (if in logging mode)")
    print("  /quit           - Exit")
    print("=" * 60 + "\n")
    
    while True:
        try:
            # Show session indicator
            session_state = agent.get_session_state()
            mode = session_state["mode"]
            date_str = session_state["target_date"] or ""
            
            if mode == "logging" and date_str:
                prompt = f"\n[You] ({date_str}) > "
            elif mode == "querying":
                prompt = "\n[You] (query) > "
            else:
                prompt = "\n[You] > "
            
            user_input = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nGoodbye!")
            break
        
        if not user_input:
            continue
        
        # Handle commands
        if user_input.startswith("/"):
            command = user_input.lower()
            
            if command == "/quit" or command == "/exit":
                print("Goodbye!")
                break
            elif command == "/tools":
                print(agent.get_tools_summary())
                continue
            elif command == "/clear":
                agent.clear_conversation()
                print("Conversation cleared.")
                continue
            elif command == "/history":
                history = agent.get_conversation_history()
                if not history:
                    print("No conversation history.")
                else:
                    print("\n" + "=" * 60)
                    print("Conversation History")
                    print("=" * 60)
                    for i, msg in enumerate(history):
                        role = msg["role"].upper()
                        print(f"\n[{role}]")
                        print("-" * 40)
                        print(msg["content"])
                        if msg.get("tool_calls"):
                            print(f"\n  Tools used: {len(msg['tool_calls'])}")
                            for tc in msg["tool_calls"]:
                                print(f"    • {tc['name']}")
                    print("\n" + "=" * 60)
                continue
            elif command.startswith("/history "):
                arg = command.split(" ", 1)[1].strip()
                if arg == "full":
                    history = agent.get_conversation_history()
                    if not history:
                        print("No conversation history.")
                    else:
                        import json
                        print("\n" + "=" * 60)
                        print("Full Conversation History (with tool details)")
                        print("=" * 60)
                        for msg in history:
                            role = msg["role"].upper()
                            print(f"\n[{role}]")
                            print("-" * 40)
                            print(msg["content"])
                            if msg.get("tool_calls"):
                                print(f"\n  Tool Calls:")
                                for tc in msg["tool_calls"]:
                                    print(f"    • {tc['name']}")
                                    args_str = json.dumps(tc['arguments'], indent=6)
                                    print(f"      Args: {args_str[:200]}{'...' if len(args_str) > 200 else ''}")
                        print("\n" + "=" * 60)
                else:
                    print(f"Unknown history option: {arg}. Use '/history' or '/history full'")
                continue
            elif command == "/session":
                state = agent.get_session_state()
                print("\nSession State:")
                print(f"  Mode: {state['mode']}")
                print(f"  Target date: {state['target_date'] or 'None'}")
                print(f"  Turn count: {state['turn_count']}")
                print(f"  Has skeleton: {state['has_skeleton']}")
                print(f"  Pending entities: {state['pending_entities']}")
                print(f"  Pending events: {state['pending_events']}")
                print(f"  Total tokens: {state['total_tokens']}")
                continue
            elif command == "/skeleton":
                skeleton = agent.get_skeleton_summary()
                if skeleton:
                    print(f"\n{skeleton}")
                else:
                    print("No skeleton loaded. Start logging for a date to build one.")
                continue
            else:
                print(f"Unknown command: {user_input}")
                continue
        
        # Send to agent
        try:
            print("\n[Agent] Thinking...")
            response = await agent.chat(user_input)
            print(f"\n[Agent]\n{response}")
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            print(f"\n[Error] {e}")


async def main() -> None:
    """Main entry point."""
    args = parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Handle list-servers command
    if args.list_servers:
        list_servers()
        return
    
    # Get LLM config
    provider = LLMProvider(args.llm)
    llm_config = get_default_llm_config(provider)
    
    if args.model:
        llm_config.model = args.model
    
    # Get MCP servers
    servers = get_selected_servers(args.servers)
    
    # Handle list-tools command
    if args.list_tools:
        await list_tools(servers)
        return
    
    # Validate API keys
    if provider == LLMProvider.CLAUDE and not llm_config.api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)
    elif provider == LLMProvider.OPENAI and not llm_config.api_key:
        print("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)
    
    # Create and run agent
    agent = CLIAgent(llm_config, servers)
    
    try:
        await agent.initialize()
        await run_interactive(agent)
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
    finally:
        await agent.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
