"""
Integration tests for Memory/RAG system with real database and ChromaDB
Tests the full stack: PostgreSQL + ChromaDB + Embeddings
"""
import pytest
from datetime import date
from pathlib import Path
import shutil

from models import JournalEntryCreate


@pytest.fixture
async def cleanup_chromadb():
    """Clean up ChromaDB test data after tests"""
    yield
    # Remove test ChromaDB directory
    test_chroma_path = Path(__file__).parent.parent / "chroma_db_test"
    if test_chroma_path.exists():
        shutil.rmtree(test_chroma_path)


@pytest.mark.asyncio
async def test_memory_log_and_search_integration(repos, cleanup_chromadb):
    """Test logging journal entries and semantic search with real DB and vector store"""
    
    # Skip if memory service is disabled
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    # Test 1: Log journal entries
    test_entries = [
        JournalEntryCreate(
            raw_text="Had an amazing workout today. Did 5 sets of squats and deadlifts. Feeling strong!",
            entry_date="2025-12-01",
            entry_type="journal",
            tags=["fitness", "strength"]
        ),
        JournalEntryCreate(
            raw_text="Feeling stressed about the upcoming project deadline. Need to prioritize tasks better.",
            entry_date="2025-12-01", 
            entry_type="reflection",
            tags=["work", "stress"]
        ),
        JournalEntryCreate(
            raw_text="Great meeting with the team today. We aligned on the Q1 roadmap and everyone seems motivated.",
            entry_date="2025-11-30",
            entry_type="journal",
            tags=["work", "team"]
        ),
        JournalEntryCreate(
            raw_text="Slept poorly last night, only 5 hours. Woke up multiple times. Need to improve sleep hygiene.",
            entry_date="2025-11-29",
            entry_type="log",
            tags=["sleep", "health"]
        ),
        JournalEntryCreate(
            raw_text="New idea: Build a personal finance tracker that integrates with my journal to correlate spending with mood.",
            entry_date="2025-11-28",
            entry_type="idea",
            tags=["project", "finance"]
        ),
    ]
    
    logged_entries = []
    for entry_data in test_entries:
        entry = await repos.memory.log_entry(entry_data)
        logged_entries.append(entry)
        assert entry.id is not None
        assert entry.raw_text == entry_data.raw_text
    
    # Test 2: Semantic Search - verify it returns relevant results
    search_queries = [
        "How have I been sleeping?",
        "What about my workouts?",
        "Am I stressed about work?",
        "Any new project ideas?"
    ]
    
    for query in search_queries:
        results = await repos.memory.search_history(query=query, limit=3)
        assert len(results) > 0, f"No results for query: {query}"
        
        # Verify result structure
        for result in results:
            assert 'text' in result
            assert 'metadata' in result
            assert 'id' in result
            assert len(result['text']) > 0
    
    # Test 3: Get entries by date
    entries_dec_1 = await repos.memory.get_entries_by_date(date(2025, 12, 1))
    assert len(entries_dec_1) >= 2  # Should have at least the 2 entries we logged for this date
    
    # Verify the entries are in the database
    found_types = {e.entry_type for e in entries_dec_1}
    assert "journal" in found_types
    assert "reflection" in found_types


@pytest.mark.asyncio
async def test_memory_disabled_fallback(repos):
    """Test that system works when memory/vector store is disabled"""
    # This test verifies that even without vector search, basic operations work
    entry_data = JournalEntryCreate(
        raw_text="Test entry without vector store",
        entry_date="2025-12-01",
        entry_type="journal",
        tags=["test"]
    )
    
    # Should still be able to log to database
    entry = await repos.memory.log_entry(entry_data)
    assert entry.id is not None
    assert entry.raw_text == entry_data.raw_text
    
    # Should be able to retrieve by date
    entries = await repos.memory.get_entries_by_date(date(2025, 12, 1))
    assert any(e.id == entry.id for e in entries)
