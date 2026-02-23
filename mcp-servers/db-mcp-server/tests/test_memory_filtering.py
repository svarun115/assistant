"""
Tests for metadata filtering in semantic search
"""
import pytest
from datetime import date

from models import JournalEntryCreate


@pytest.fixture
async def diverse_journal_entries(repos):
    """Create entries with diverse dates, types, and tags"""
    
    entries = [
        # 2024 fitness entries
        JournalEntryCreate(
            raw_text="Great workout today! Heavy squats and deadlifts.",
            entry_date="2024-06-15",
            entry_type="journal",
            tags=["fitness", "strength"]
        ),
        JournalEntryCreate(
            raw_text="Reflecting on my fitness journey. I've come so far!",
            entry_date="2024-08-20",
            entry_type="reflection",
            tags=["fitness", "progress"]
        ),
        
        # 2025 work entries
        JournalEntryCreate(
            raw_text="Project deadline is approaching. Feeling stressed but focused.",
            entry_date="2025-01-10",
            entry_type="journal",
            tags=["work", "stress"]
        ),
        JournalEntryCreate(
            raw_text="Great insight today: breaking tasks into smaller pieces reduces anxiety.",
            entry_date="2025-02-05",
            entry_type="reflection",
            tags=["work", "productivity"]
        ),
        
        # 2025 project ideas
        JournalEntryCreate(
            raw_text="New app idea: AI-powered personal journal that correlates mood with activities.",
            entry_date="2025-03-15",
            entry_type="idea",
            tags=["project", "ai", "health"]
        ),
        JournalEntryCreate(
            raw_text="Brainstorming: What if I built a smart home automation system?",
            entry_date="2025-04-01",
            entry_type="idea",
            tags=["project", "smart-home"]
        ),
        
        # Recent sleep logs
        JournalEntryCreate(
            raw_text="Terrible sleep last night. Only 4 hours, woke up multiple times.",
            entry_date="2025-11-20",
            entry_type="log",
            tags=["sleep", "health"]
        ),
        JournalEntryCreate(
            raw_text="Best sleep in weeks! 8 solid hours, feeling refreshed.",
            entry_date="2025-11-28",
            entry_type="log",
            tags=["sleep", "health"]
        ),
    ]
    
    logged = []
    for entry_data in entries:
        entry = await repos.memory.log_entry(entry_data)
        logged.append(entry)
    
    return logged


@pytest.mark.asyncio
async def test_filter_by_date_range(repos, diverse_journal_entries):
    """Test filtering by date range"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    # Search only 2024 entries
    results = await repos.memory.search_history(
        query="fitness workout",
        limit=10,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31)
    )
    
    assert len(results) > 0, "Should find 2024 fitness entries"
    
    # Verify all results are from 2024
    for r in results:
        entry_date = r['metadata']['date']
        assert entry_date.startswith('2024'), f"Expected 2024 entry, got {entry_date}"


@pytest.mark.asyncio
async def test_filter_by_entry_type(repos, diverse_journal_entries):
    """Test filtering by entry type"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    # Search only for ideas
    results = await repos.memory.search_history(
        query="new projects",
        limit=10,
        entry_types=["idea"]
    )
    
    assert len(results) > 0, "Should find idea entries"
    
    # Verify all results are ideas
    for r in results:
        assert r['metadata']['type'] == 'idea', f"Expected idea, got {r['metadata']['type']}"


@pytest.mark.asyncio
async def test_filter_by_multiple_entry_types(repos, diverse_journal_entries):
    """Test filtering by multiple entry types"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    # Search for reflections and ideas only
    results = await repos.memory.search_history(
        query="thinking about work and projects",
        limit=10,
        entry_types=["reflection", "idea"]
    )
    
    assert len(results) > 0, "Should find reflection or idea entries"
    
    # Verify all results are either reflections or ideas
    for r in results:
        entry_type = r['metadata']['type']
        assert entry_type in ['reflection', 'idea'], f"Expected reflection/idea, got {entry_type}"


@pytest.mark.asyncio
async def test_filter_by_tags(repos, diverse_journal_entries):
    """Test filtering by tags"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    # Search only entries tagged with 'health'
    # Use a query that semantically matches the health-tagged entry about AI journal
    results = await repos.memory.search_history(
        query="AI mood tracking journal",
        limit=10,
        tags=["health"]
    )
    
    assert len(results) > 0, "Should find health-tagged entries"
    
    # Verify all results have the 'health' tag
    for r in results:
        entry_tags = r['metadata'].get('tags', '').split(',')
        entry_tags = [t.strip() for t in entry_tags if t.strip()]
        assert 'health' in entry_tags, f"Expected 'health' tag, got {entry_tags}"


@pytest.mark.asyncio
async def test_filter_by_multiple_tags(repos, diverse_journal_entries):
    """Test filtering with multiple tags (OR condition)"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    # Search entries with either 'work' or 'project' tags
    # Use a query that matches both work stress and project ideas
    results = await repos.memory.search_history(
        query="deadline productivity automation",
        limit=10,
        tags=["work", "project"]
    )
    
    assert len(results) > 0, "Should find work or project entries"
    
    # Verify all results have at least one of the specified tags
    for r in results:
        entry_tags = r['metadata'].get('tags', '').split(',')
        entry_tags = [t.strip() for t in entry_tags if t.strip()]
        has_tag = any(tag in entry_tags for tag in ["work", "project"])
        assert has_tag, f"Expected work or project tag, got {entry_tags}"


@pytest.mark.asyncio
async def test_combined_filters(repos, diverse_journal_entries):
    """Test combining multiple filters"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    # Search 2025 reflections about work
    results = await repos.memory.search_history(
        query="work productivity stress",
        limit=10,
        start_date=date(2025, 1, 1),
        entry_types=["reflection"],
        tags=["work"]
    )
    
    assert len(results) > 0, "Should find 2025 work reflections"
    
    # Verify all filters are applied
    for r in results:
        # Check date
        entry_date = r['metadata']['date']
        assert entry_date.startswith('2025'), f"Expected 2025, got {entry_date}"
        
        # Check type
        assert r['metadata']['type'] == 'reflection', f"Expected reflection, got {r['metadata']['type']}"
        
        # Check tag
        entry_tags = r['metadata'].get('tags', '').split(',')
        entry_tags = [t.strip() for t in entry_tags if t.strip()]
        assert 'work' in entry_tags, f"Expected 'work' tag, got {entry_tags}"


@pytest.mark.asyncio
async def test_no_filters_returns_all_relevant(repos, diverse_journal_entries):
    """Test that search without filters returns all relevant results"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    # Search without filters
    results_unfiltered = await repos.memory.search_history(
        query="sleep quality",
        limit=10
    )
    
    # Search with broad date filter
    results_filtered = await repos.memory.search_history(
        query="sleep quality",
        limit=10,
        start_date=date(2025, 1, 1)
    )
    
    # Unfiltered should return more or equal results
    assert len(results_unfiltered) >= len(results_filtered), \
        "Unfiltered search should return at least as many results as filtered"


@pytest.mark.asyncio
async def test_filter_with_no_matches(repos, diverse_journal_entries):
    """Test that filters correctly return no results when nothing matches"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    # Search for a tag that doesn't exist
    results = await repos.memory.search_history(
        query="anything",
        limit=10,
        tags=["nonexistent-tag"]
    )
    
    assert len(results) == 0, "Should return no results for non-existent tag"
    
    # Search in a date range with no entries
    results = await repos.memory.search_history(
        query="anything",
        limit=10,
        start_date=date(2020, 1, 1),
        end_date=date(2020, 12, 31)
    )
    
    assert len(results) == 0, "Should return no results for date range with no entries"
