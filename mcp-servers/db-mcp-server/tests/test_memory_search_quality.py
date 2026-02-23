"""
Tests for semantic search quality and relevance
Evaluates whether the vector search returns appropriate results
"""
import pytest
from datetime import date

from models import JournalEntryCreate


@pytest.fixture
async def populated_journal(repos):
    """Create a diverse set of journal entries for search testing"""
    
    entries = [
        # Fitness entries
        JournalEntryCreate(
            raw_text="Crushed leg day! 5x5 squats at 225lbs, 3x8 deadlifts at 275lbs. Feeling incredibly strong and energized.",
            entry_date="2025-11-01",
            entry_type="journal",
            tags=["fitness", "strength", "legs"]
        ),
        JournalEntryCreate(
            raw_text="Morning run: 5 miles in 42 minutes. Beautiful weather, felt great. Need to do this more often.",
            entry_date="2025-11-05",
            entry_type="journal",
            tags=["fitness", "cardio", "running"]
        ),
        
        # Sleep entries
        JournalEntryCreate(
            raw_text="Terrible night. Only got 4 hours of sleep, woke up 3 times. Felt groggy all day. Need to fix my sleep schedule.",
            entry_date="2025-11-10",
            entry_type="log",
            tags=["sleep", "health"]
        ),
        JournalEntryCreate(
            raw_text="Best sleep in weeks! 8 solid hours, no interruptions. Woke up feeling refreshed and ready to tackle the day.",
            entry_date="2025-11-15",
            entry_type="log",
            tags=["sleep", "health"]
        ),
        
        # Work/stress entries
        JournalEntryCreate(
            raw_text="Project deadline is killing me. So much stress. Need to break tasks down and prioritize better. Feeling overwhelmed.",
            entry_date="2025-11-20",
            entry_type="reflection",
            tags=["work", "stress"]
        ),
        JournalEntryCreate(
            raw_text="Amazing team meeting today! Everyone aligned on Q1 roadmap. Feeling motivated and energized about our direction.",
            entry_date="2025-11-22",
            entry_type="journal",
            tags=["work", "team"]
        ),
        
        # Ideas/projects
        JournalEntryCreate(
            raw_text="New app idea: Personal finance tracker that uses AI to correlate spending patterns with mood and journal entries.",
            entry_date="2025-11-25",
            entry_type="idea",
            tags=["project", "finance", "ai"]
        ),
        JournalEntryCreate(
            raw_text="Thinking about building a smart home automation system. Could integrate with my journal to track energy usage patterns.",
            entry_date="2025-11-26",
            entry_type="idea",
            tags=["project", "smart-home"]
        ),
        
        # Social/relationships
        JournalEntryCreate(
            raw_text="Great dinner with Sarah and Mike. Laughed so much my face hurt. These friendships mean everything to me.",
            entry_date="2025-11-27",
            entry_type="journal",
            tags=["social", "friends"]
        ),
        
        # Food/nutrition
        JournalEntryCreate(
            raw_text="Meal prep Sunday! Made healthy lunches for the week: grilled chicken, quinoa, roasted vegetables. Feeling organized.",
            entry_date="2025-11-28",
            entry_type="log",
            tags=["food", "health", "meal-prep"]
        ),
    ]
    
    logged = []
    for entry_data in entries:
        entry = await repos.memory.log_entry(entry_data)
        logged.append(entry)
    
    return logged


@pytest.mark.asyncio
async def test_search_fitness_queries(repos, populated_journal):
    """Test that fitness queries return fitness-related entries"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    queries = [
        "workout routine",
        "exercise performance",
        "strength training",
        "leg day",
        "running cardio"
    ]
    
    for query in queries:
        results = await repos.memory.search_history(query=query, limit=3)
        assert len(results) > 0, f"No results for fitness query: {query}"
        
        # At least one of top 3 should mention fitness/exercise keywords
        fitness_keywords = ["workout", "exercise", "squat", "deadlift", "run", "miles", "training", "fitness", "leg day"]
        found_fitness = any(
            any(kw in r['text'].lower() for kw in fitness_keywords)
            for r in results
        )
        assert found_fitness, f"No fitness-related results for query: {query}\nGot: {[r['text'][:50] for r in results]}"


@pytest.mark.asyncio
async def test_search_sleep_queries(repos, populated_journal):
    """Test that sleep queries return sleep-related entries"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    queries = [
        "how am I sleeping",
        "sleep quality",
        "insomnia problems",
        "restful night"
    ]
    
    for query in queries:
        results = await repos.memory.search_history(query=query, limit=3)
        assert len(results) > 0, f"No results for sleep query: {query}"
        
        # At least one of top 3 should mention sleep
        sleep_keywords = ["sleep", "woke", "night", "hours", "groggy", "refreshed", "insomnia"]
        found_sleep = any(
            any(kw in r['text'].lower() for kw in sleep_keywords)
            for r in results
        )
        assert found_sleep, f"No sleep-related results for query: {query}\nGot: {[r['text'][:50] for r in results]}"


@pytest.mark.asyncio
async def test_search_work_stress_queries(repos, populated_journal):
    """Test that work/stress queries return relevant entries"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    queries = [
        "feeling stressed",
        "work pressure",
        "deadline anxiety",
        "team collaboration"
    ]
    
    for query in queries:
        results = await repos.memory.search_history(query=query, limit=3)
        assert len(results) > 0, f"No results for work query: {query}"
        
        # Should contain work-related keywords
        work_keywords = ["work", "stress", "deadline", "project", "team", "meeting", "overwhelmed", "motivated"]
        found_work = any(
            any(kw in r['text'].lower() for kw in work_keywords)
            for r in results
        )
        assert found_work, f"No work-related results for query: {query}\nGot: {[r['text'][:50] for r in results]}"


@pytest.mark.asyncio
async def test_search_project_ideas_queries(repos, populated_journal):
    """Test that project/idea queries return idea entries"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    queries = [
        "new project ideas",
        "app concepts",
        "things to build",
        "creative projects"
    ]
    
    for query in queries:
        results = await repos.memory.search_history(query=query, limit=3)
        assert len(results) > 0, f"No results for ideas query: {query}"
        
        # Should contain idea/project keywords
        idea_keywords = ["idea", "build", "project", "app", "system", "tracker", "automation", "thinking about"]
        found_ideas = any(
            any(kw in r['text'].lower() for kw in idea_keywords)
            for r in results
        )
        assert found_ideas, f"No idea-related results for query: {query}\nGot: {[r['text'][:50] for r in results]}"


@pytest.mark.asyncio
async def test_search_specificity(repos, populated_journal):
    """Test that specific queries return more specific results than general queries"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    # Very specific query should return very relevant result
    results = await repos.memory.search_history(query="deadlift squat leg workout", limit=1)
    assert len(results) > 0
    
    top_result = results[0]['text'].lower()
    # The leg day entry should be most relevant
    assert "squat" in top_result or "deadlift" in top_result or "leg" in top_result, \
        f"Specific strength query didn't return strength entry. Got: {results[0]['text']}"


@pytest.mark.asyncio
async def test_search_score_ordering(repos, populated_journal):
    """Test that results are ordered by relevance (lower distance = more relevant in cosine)"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    results = await repos.memory.search_history(query="physical exercise fitness", limit=5)
    
    if len(results) >= 2 and results[0]['score'] is not None and results[1]['score'] is not None:
        # ChromaDB returns distances where lower = more similar (for cosine)
        # So scores should be in ascending order (or at least not strictly descending)
        scores = [r['score'] for r in results if r['score'] is not None]
        # Verify they are sorted (allowing for ties)
        for i in range(len(scores) - 1):
            assert scores[i] <= scores[i+1] + 0.001, f"Results not properly sorted by relevance score: {scores}"


@pytest.mark.asyncio
async def test_search_avoids_irrelevant_results(repos, populated_journal):
    """Test that highly specific queries don't return completely irrelevant results"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    # Query about running should not return project ideas as top result
    results = await repos.memory.search_history(query="morning jog run cardio", limit=3)
    assert len(results) > 0
    
    # At least one of the top 3 should be about running/cardio, not completely different topics
    running_keywords = ["run", "miles", "cardio", "jog", "morning"]
    has_relevant = any(
        any(kw in r['text'].lower() for kw in running_keywords)
        for r in results
    )
    
    assert has_relevant, f"Running query returned irrelevant results: {[r['text'][:60] for r in results]}"


@pytest.mark.asyncio
async def test_embedding_model_quality(repos):
    """Verify the embedding model is loaded and working"""
    if not repos.memory.config.enabled:
        pytest.skip("Memory service is disabled")
    
    # Test that the model can generate embeddings
    assert repos.memory.embedding_model is not None
    
    # Generate test embeddings
    embedding1 = repos.memory._generate_embedding("I love running and cardio exercise")
    embedding2 = repos.memory._generate_embedding("I enjoy jogging and aerobic workouts")
    embedding3 = repos.memory._generate_embedding("The stock market crashed today")
    
    # Embeddings should be vectors of the right size (384 for all-MiniLM-L6-v2)
    assert len(embedding1) == 384
    assert len(embedding2) == 384
    assert len(embedding3) == 384
    
    # Similar sentences should have more similar embeddings
    import numpy as np
    
    def cosine_similarity(a, b):
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
    
    sim_12 = cosine_similarity(embedding1, embedding2)  # Similar topics
    sim_13 = cosine_similarity(embedding1, embedding3)  # Different topics
    
    # Similar sentences should be more similar than dissimilar ones
    assert sim_12 > sim_13, f"Similar topics not more similar: sim(running,jogging)={sim_12:.3f} vs sim(running,stocks)={sim_13:.3f}"
