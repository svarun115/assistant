import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date, datetime
from uuid import uuid4

from handlers.journal_handlers import (
    handle_log_journal_entry,
    handle_search_journal_history,
    handle_get_journal_by_date
)
from models import JournalEntry

@pytest.fixture
def mock_repos():
    repos = MagicMock()
    repos.memory = AsyncMock()
    return repos

@pytest.mark.asyncio
async def test_handle_log_journal_entry(mock_repos):
    """Test logging a journal entry via handler"""
    # Arrange
    args = {
        "text": "My journal entry",
        "entry_type": "reflection",
        "tags": ["life"],
        "entry_date": "2025-11-29"
    }
    
    mock_entry = JournalEntry(
        id=uuid4(),
        raw_text="My journal entry",
        entry_date="2025-11-29",
        entry_timestamp=datetime(2025, 11, 29, 10, 0),
        entry_type="reflection",
        tags=["life"],
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    mock_repos.memory.log_entry.return_value = mock_entry
    
    # Act
    result = await handle_log_journal_entry(args, mock_repos)
    
    # Assert
    assert len(result) == 1
    assert "Successfully logged entry" in result[0].text
    mock_repos.memory.log_entry.assert_called_once()
    call_arg = mock_repos.memory.log_entry.call_args[0][0]
    assert call_arg.raw_text == "My journal entry"
    assert call_arg.entry_type == "reflection"

@pytest.mark.asyncio
async def test_handle_search_journal_history(mock_repos):
    """Test searching journal history via handler"""
    # Arrange
    args = {"query": "test query"}
    
    mock_repos.memory.search_history.return_value = [
        {
            "id": "1",
            "text": "Found entry",
            "metadata": {"date": "2025-01-01", "type": "journal"},
            "score": 0.1
        }
    ]
    
    # Act
    result = await handle_search_journal_history(args, mock_repos)
    
    # Assert
    assert len(result) == 1
    assert "Found the following relevant entries" in result[0].text
    assert "Found entry" in result[0].text
    mock_repos.memory.search_history.assert_called_once_with(
        query="test query",
        limit=5,
        start_date=None,
        end_date=None,
        entry_types=None,
        tags=None
    )

@pytest.mark.asyncio
async def test_handle_get_journal_by_date(mock_repos):
    """Test getting journal by date via handler"""
    # Arrange
    args = {"entry_date": "2025-11-29"}
    
    mock_entry = JournalEntry(
        id=uuid4(),
        raw_text="Daily log",
        entry_date="2025-11-29",
        entry_timestamp=datetime(2025, 11, 29, 10, 0),
        entry_type="log",
        tags=[],
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    mock_repos.memory.get_entries_by_date.return_value = [mock_entry]
    
    # Act
    result = await handle_get_journal_by_date(args, mock_repos)
    
    # Assert
    assert len(result) == 1
    assert "Journal Entries for 2025-11-29" in result[0].text
    assert "Daily log" in result[0].text
