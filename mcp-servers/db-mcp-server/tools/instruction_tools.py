"""
Instruction Tools
Tools for retrieving system instructions and documentation.
"""

from mcp import types

# Valid domains for get_domain_instructions
VALID_DOMAINS = ["meals", "events", "workouts", "people", "locations", "travel", "entertainment", "journal"]


def get_journal_instructions() -> types.Tool:
    """Create tool definition for get_journal_instructions"""
    return types.Tool(
        name="get_journal_instructions",
        description="Get the complete system instructions for using the Personal Journal Database. Call this first to understand the database schema, available tools, workflow patterns, and best practices.",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": []
        }
    )


def get_domain_instructions() -> types.Tool:
    """Create tool definition for get_domain_instructions"""
    return types.Tool(
        name="get_domain_instructions",
        description=f"Get detailed instructions for a specific domain. Use this to learn about domain-specific workflows, field requirements, and examples. Valid domains: {', '.join(VALID_DOMAINS)}",
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": f"The domain to get instructions for. Valid values: {', '.join(VALID_DOMAINS)}",
                    "enum": VALID_DOMAINS
                }
            },
            "required": ["domain"]
        }
    )
