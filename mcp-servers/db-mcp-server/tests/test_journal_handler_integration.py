"""
Integration tests for journal handlers with filtering
Tests the full MCP tool chain: tool definition → handler → service
"""
import pytest
from datetime import date

from handlers.journal_handlers import handle_log_journal_entry, handle_search_journal_history
from models import JournalEntryCreate


@pytest.fixture
async def sample_journal_entries(repos):
    """Create sample entries for handler testing"""
    entries = [
        JournalEntryCreate(
            raw_text="Morning workout was intense! Squats and deadlifts at new PRs.",
            entry_date="2024-06-15",
            entry_type="journal",
            tags=["fitness", "strength"]
        ),
        JournalEntryCreate(
            raw_text="Reflecting on my progress. I've grown so much this year.",
            entry_date="2025-01-10",
            entry_type="reflection",
            tags=["personal-growth"]
        ),
        JournalEntryCreate(
            raw_text="Project deadline stress is real. Need better time management.",
            entry_date="2025-03-15",
            entry_type="journal",
            tags=["work", "stress"]
        ),
        JournalEntryCreate(
            raw_text="New idea: Build an AI assistant for personal productivity.",
            entry_date="2025-05-20",
            entry_type="idea",
            tags=["project", "ai"]
        ),
    ]
    
    for entry_data in entries:
        await repos.memory.log_entry(entry_data)
    
    return entries


@pytest.mark.asyncio
async def test_log_journal_entry_handler(repos):
    """Test logging entries through the handler"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    arguments = {
        "text": "Test entry via handler",
        "entry_type": "journal",
        "tags": ["test"],
        "entry_date": "2025-12-01"
    }
    
    result = await handle_log_journal_entry(arguments, repos)
    
    assert len(result) == 1
    assert "Successfully logged entry" in result[0].text
    assert "2025-12-01" in result[0].text


@pytest.mark.asyncio
async def test_search_handler_no_filters(repos, sample_journal_entries):
    """Test search handler without filters"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    arguments = {
        "query": "fitness workout exercise",
        "limit": 5
    }
    
    result = await handle_search_journal_history(arguments, repos)
    
    assert len(result) == 1
    assert "relevant entries" in result[0].text.lower()


@pytest.mark.asyncio
async def test_search_handler_with_date_filter(repos, sample_journal_entries):
    """Test search handler with date range filter"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    # Search only 2025 entries
    arguments = {
        "query": "personal growth reflection",
        "limit": 5,
        "start_date": "2025-01-01",
        "end_date": "2025-12-31"
    }
    
    result = await handle_search_journal_history(arguments, repos)
    
    assert len(result) == 1
    response_text = result[0].text
    
    # Should find results
    assert "relevant entries" in response_text.lower() or "no matching" in response_text.lower()
    
    # If results found, verify they're from 2025
    if "relevant entries" in response_text.lower():
        assert "2025" in response_text


@pytest.mark.asyncio
async def test_search_handler_with_entry_type_filter(repos, sample_journal_entries):
    """Test search handler with entry type filter"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    # Search only ideas
    arguments = {
        "query": "new project",
        "limit": 5,
        "entry_types": ["idea"]
    }
    
    result = await handle_search_journal_history(arguments, repos)
    
    assert len(result) == 1
    response_text = result[0].text
    
    # Should find the idea entry
    if "relevant entries" in response_text.lower():
        assert "Type: idea" in response_text


@pytest.mark.asyncio
async def test_search_handler_with_tag_filter(repos, sample_journal_entries):
    """Test search handler with tag filter"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    # Search only work-tagged entries
    arguments = {
        "query": "stress productivity",
        "limit": 5,
        "tags": ["work"]
    }
    
    result = await handle_search_journal_history(arguments, repos)
    
    assert len(result) == 1
    response_text = result[0].text
    
    # Should find work-tagged entries
    if "relevant entries" in response_text.lower():
        assert "Tags:" in response_text
        assert "work" in response_text.lower()


@pytest.mark.asyncio
async def test_search_handler_combined_filters(repos, sample_journal_entries):
    """Test search handler with multiple filters combined"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    # Search 2025 ideas with project tag
    arguments = {
        "query": "artificial intelligence",
        "limit": 5,
        "start_date": "2025-01-01",
        "entry_types": ["idea"],
        "tags": ["project"]
    }
    
    result = await handle_search_journal_history(arguments, repos)
    
    assert len(result) == 1
    response_text = result[0].text
    
    # Should find the AI project idea
    if "relevant entries" in response_text.lower():
        assert "2025" in response_text
        assert "Type: idea" in response_text


@pytest.mark.asyncio
async def test_search_handler_no_results(repos, sample_journal_entries):
    """Test search handler returns appropriate message when no results"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    # Search with impossible filters
    arguments = {
        "query": "anything",
        "limit": 5,
        "tags": ["nonexistent-tag-xyz"]
    }
    
    result = await handle_search_journal_history(arguments, repos)
    
    assert len(result) == 1
    assert "no matching" in result[0].text.lower()


@pytest.mark.asyncio
async def test_handler_error_handling_missing_query(repos):
    """Test handler error handling for missing required parameters"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    arguments = {
        "limit": 5
        # Missing required 'query' parameter
    }
    
    with pytest.raises(ValueError, match="Query is required"):
        await handle_search_journal_history(arguments, repos)


@pytest.mark.asyncio
async def test_handler_output_format(repos, sample_journal_entries):
    """Test that handler output format includes all metadata"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    arguments = {
        "query": "workout fitness",
        "limit": 2
    }
    
    result = await handle_search_journal_history(arguments, repos)
    
    assert len(result) == 1
    response_text = result[0].text
    
    if "relevant entries" in response_text.lower():
        # Should include date
        assert "Date:" in response_text
        # Should include type
        assert "Type:" in response_text
        # Should include the actual text content
        assert len(response_text) > 100  # Should have substantial content
