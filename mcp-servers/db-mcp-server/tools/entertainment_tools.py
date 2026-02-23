"""
Entertainment MCP Tools
Specialized tools for tracking entertainment consumption (movies, TV, videos, podcasts, etc.).
"""

from mcp import types


def get_entertainment_tools() -> list[types.Tool]:
    """
    Returns entertainment logging tools.
    
    Tools included:
    - create_entertainment: Log entertainment consumption with event
    
    For querying entertainment history, use execute_sql_query instead (SQL-first architecture).
    """
    return [
        _create_entertainment_tool(),
    ]


def _create_entertainment_tool() -> types.Tool:
    """Create entertainment with event (movies, TV shows, videos, podcasts, live performances, gaming, reading, etc.)."""
    return types.Tool(
        name="create_entertainment",
        description="""Log entertainment consumption (movies, TV shows, YouTube videos, podcasts, live performances, gaming, reading, etc.).

Record what you've watched, played, read, or attended with ratings and notes. Creates an event and entertainment specialization.

EXAMPLE - Movie:
{
  "event": {
    "title": "Watched Oppenheimer",
    "start_time": "2025-10-15T19:00:00",
    "end_time": "2025-10-15T22:00:00",
    "event_type": "generic",
    "category": "entertainment"
  },
  "entertainment": {
    "entertainment_type": "movie",
    "title": "Oppenheimer",
    "director": "Christopher Nolan",
    "release_year": 2023,
    "personal_rating": 9,
    "completion_status": "finished"
  }
}

EXAMPLE - TV Show:
{
  "event": {
    "title": "Watched Severance",
    "start_time": "2025-06-28T16:30:00",
    "end_time": "2025-06-28T18:00:00"
  },
  "entertainment": {
    "entertainment_type": "tv_show",
    "title": "Severance",
    "show_name": "Severance",
    "season_number": 1,
    "episode_number": 1,
    "episode_title": "Good News About Hell",
    "personal_rating": 9,
    "completion_status": "in_progress"
  }
}

EXAMPLE - YouTube Video:
{
  "event": {
    "title": "Watched tech review",
    "start_time": "2025-10-15T14:30:00"
  },
  "entertainment": {
    "entertainment_type": "video",
    "title": "MacBook Pro M3 Review",
    "channel_name": "MKBHD",
    "video_url": "https://youtube.com/watch?v=abc123",
    "personal_rating": 8
  }
}""",
        inputSchema={
            "type": "object",
            "properties": {
                "event": {
                    "type": "object",
                    "description": "Event details (WHO, WHERE, WHEN)",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Event title (e.g., 'Watched Oppenheimer', 'Played Zelda')"
                        },
                        "start_time": {
                            "type": "string",
                            "description": "Start time (ISO 8601: YYYY-MM-DDTHH:MM:SS)"
                        },
                        "end_time": {
                            "type": "string",
                            "description": "End time (ISO 8601, optional)"
                        },
                        "event_type": {
                            "type": "string",
                            "description": "Event type (default: 'generic')",
                            "enum": ["generic", "entertainment"]
                        },
                        "category": {
                            "type": "string",
                            "enum": ["health", "social", "work", "travel", "personal", "family", "media", "education", "maintenance", "interaction", "entertainment", "other"],
                            "description": "Event category. Default: entertainment"
                        },
                        "location_id": {
                            "type": "string",
                            "description": "Location UUID (if known)"
                        },
                        "participant_ids": {
                            "type": "array",
                            "description": "Participant UUIDs (if watched with others)",
                            "items": {"type": "string"}
                        },
                        "description": {
                            "type": "string",
                            "description": "Event description (optional)"
                        },
                        "notes": {
                            "type": "string",
                            "description": "Event notes (optional)"
                        },
                        "tags": {
                            "type": "array",
                            "description": "Event tags (optional)",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["title", "start_time"]
                },
                "entertainment": {
                    "type": "object",
                    "description": "Entertainment details (WHAT)",
                    "properties": {
                        "entertainment_type": {
                            "type": "string",
                            "description": "Type of entertainment",
                            "enum": ["movie", "tv_show", "video", "podcast", "live_performance", "gaming", "reading", "streaming", "concert", "theater", "sports_event", "other"]
                        },
                        "title": {
                            "type": "string",
                            "description": "Title of the entertainment (movie name, show name, book title, etc.)"
                        },
                        "creator": {
                            "type": "string",
                            "description": "Creator/author (optional)"
                        },
                        "genre": {
                            "type": "string",
                            "description": "Genre (optional)"
                        },
                        "show_name": {
                            "type": "string",
                            "description": "Show name (for TV shows, optional)"
                        },
                        "season_number": {
                            "type": "integer",
                            "description": "Season number (for TV shows, optional)"
                        },
                        "episode_number": {
                            "type": "integer",
                            "description": "Episode number (for TV shows, optional)"
                        },
                        "episode_title": {
                            "type": "string",
                            "description": "Episode title (for TV shows, optional)"
                        },
                        "channel_name": {
                            "type": "string",
                            "description": "Channel/creator name (for videos/podcasts, optional)"
                        },
                        "video_url": {
                            "type": "string",
                            "description": "Video URL (for online content, optional)"
                        },
                        "director": {
                            "type": "string",
                            "description": "Director (for movies, optional)"
                        },
                        "release_year": {
                            "type": "integer",
                            "description": "Release year (optional)"
                        },
                        "performance_type": {
                            "type": "string",
                            "description": "Performance type (for live performances, optional)",
                            "enum": ["concert", "theater", "comedy", "dance", "opera", "sports", "other"]
                        },
                        "venue": {
                            "type": "string",
                            "description": "Venue name (for live performances, optional)"
                        },
                        "performer_artist": {
                            "type": "string",
                            "description": "Performer/artist name (optional)"
                        },
                        "game_platform": {
                            "type": "string",
                            "description": "Gaming platform (for games, optional)"
                        },
                        "game_genre": {
                            "type": "string",
                            "description": "Game genre (optional)"
                        },
                        "platform": {
                            "type": "string",
                            "description": "Platform/service (Netflix, Spotify, etc., optional)"
                        },
                        "format": {
                            "type": "string",
                            "description": "Format (digital, physical, streaming, optional)"
                        },
                        "personal_rating": {
                            "type": "integer",
                            "description": "Personal rating (1-10, optional)",
                            "minimum": 1,
                            "maximum": 10
                        },
                        "completion_status": {
                            "type": "string",
                            "description": "Completion status (optional)",
                            "enum": ["started", "finished", "abandoned", "in_progress"]
                        },
                        "rewatch": {
                            "type": "boolean",
                            "description": "Is this a rewatch? (optional)"
                        },
                        "watched_with_others": {
                            "type": "boolean",
                            "description": "Watched with others? (optional)"
                        }
                    },
                    "required": ["entertainment_type", "title"]
                }
            },
            "required": ["event", "entertainment"]
        }
    )
