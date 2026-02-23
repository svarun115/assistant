"""
Instruction Handlers
Handle MCP tool calls for retrieving system instructions and documentation.
"""

import logging
from pathlib import Path
from typing import Any
from mcp import types

logger = logging.getLogger(__name__)

# Valid domains matching mcp/resources/ files
VALID_DOMAINS = ["meals", "events", "workouts", "people", "locations", "travel", "entertainment", "journal"]


async def handle_get_journal_instructions(arguments: dict[str, Any]) -> list[types.TextContent]:
    """
    Get the complete system instructions for using the Personal Journal Database.
    
    Returns combined content from CAPABILITIES.md, WORKFLOW.md, and EXAMPLES.md.
    """
    try:
        prompts_dir = Path(__file__).parent.parent / "mcp" / "prompts"
        files_to_load = ["CAPABILITIES.md", "WORKFLOW.md", "EXAMPLES.md"]
        content_parts = []
        
        for filename in files_to_load:
            file_path = prompts_dir / filename
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    content_parts.append(f.read())
            else:
                logger.warning(f"Instruction file not found: {filename}")
        
        if not content_parts:
            return [types.TextContent(
                type="text",
                text="ERROR: No instruction files found. Please check the mcp/prompts/ directory."
            )]
        
        full_content = "\n\n---\n\n".join(content_parts)
        
        return [types.TextContent(
            type="text",
            text=full_content
        )]
        
    except Exception as e:
        logger.error(f"Failed to load instructions: {e}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=f"ERROR: Could not load instructions: {str(e)}"
        )]


async def handle_get_domain_instructions(arguments: dict[str, Any]) -> list[types.TextContent]:
    """
    Get detailed instructions for a specific domain.
    
    Reads content from mcp/resources/{DOMAIN}.md files.
    """
    try:
        domain = arguments.get("domain", "").lower()
        
        if not domain:
            return [types.TextContent(
                type="text",
                text=f"ERROR: 'domain' parameter is required. Valid domains: {', '.join(VALID_DOMAINS)}"
            )]
        
        if domain not in VALID_DOMAINS:
            return [types.TextContent(
                type="text",
                text=f"ERROR: Invalid domain '{domain}'. Valid domains: {', '.join(VALID_DOMAINS)}"
            )]
        
        resources_dir = Path(__file__).parent.parent / "mcp" / "resources"
        file_path = resources_dir / f"{domain.upper()}.md"
        
        if not file_path.exists():
            return [types.TextContent(
                type="text",
                text=f"ERROR: Instructions not found for domain '{domain}'. File missing: {file_path.name}"
            )]
        
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        return [types.TextContent(
            type="text",
            text=content
        )]
        
    except Exception as e:
        logger.error(f"Failed to load domain instructions: {e}", exc_info=True)
        return [types.TextContent(
            type="text",
            text=f"ERROR: Could not load domain instructions: {str(e)}"
        )]
