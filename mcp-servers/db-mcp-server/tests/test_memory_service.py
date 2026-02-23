import pytest
import sys
from datetime import date, datetime
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from models import JournalEntryCreate, JournalEntry
from services.memory_service import MemoryService
from config import MemoryConfig

@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    repo.create = AsyncMock()
    repo.get_by_date = AsyncMock()
    return repo

@pytest.fixture
def memory_service(mock_repo):
    config = MemoryConfig(enabled=False) # Disable vector store for unit tests
    return MemoryService(mock_repo, config)

@pytest.mark.asyncio
async def test_log_entry_db_only(memory_service, mock_repo):
    """Test logging entry to DB only (vector store disabled)"""
    # Arrange
    entry_data = JournalEntryCreate(
        raw_text="Test entry",
        entry_date="2025-01-01",
        entry_type="journal",
        tags=["test"]
    )
    
    expected_entry = JournalEntry(
        id=uuid4(),
        raw_text="Test entry",
        entry_date="2025-01-01",
        entry_timestamp=datetime(2025, 1, 1, 12, 0),
        entry_type="journal",
        tags=["test"],
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    mock_repo.create.return_value = expected_entry
    
    # Act
    result = await memory_service.log_entry(entry_data)
    
    # Assert
    assert result == expected_entry
    mock_repo.create.assert_called_once_with(entry_data)

@pytest.mark.asyncio
async def test_log_entry_with_vector_store(mock_repo):
    """Test logging entry with vector store enabled"""
    # Arrange
    config = MemoryConfig(enabled=True)
    
    # Mock lazy imports
    mock_chroma = MagicMock()
    mock_sentence_transformer = MagicMock()
    
    with patch.dict(sys.modules, {
        'chromadb': mock_chroma,
        'chromadb.config': MagicMock(),
        'sentence_transformers': mock_sentence_transformer
    }):
        # Mock Vector Store setup
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_chroma.PersistentClient.return_value = mock_client
        mock_client.get_or_create_collection.return_value = mock_collection
        
        # Mock Embedding Model
        mock_model = MagicMock()
        mock_model.encode.return_value.tolist.return_value = [0.1, 0.2, 0.3]
        mock_sentence_transformer.SentenceTransformer.return_value = mock_model
        
        service = MemoryService(mock_repo, config)
        
        # Mock DB Return
        entry_data = JournalEntryCreate(
            raw_text="Test vector",
            entry_date="2025-01-01",
            entry_type="journal",
            tags=["test"]
        )
        expected_entry = JournalEntry(
            id=uuid4(),
            raw_text="Test vector",
            entry_date="2025-01-01",
            entry_timestamp=datetime(2025, 1, 1, 12, 0),
            entry_type="journal",
            tags=["test"],
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        mock_repo.create.return_value = expected_entry
        
        # Act
        await service.log_entry(entry_data)
        
        # Assert
        # 1. DB called
        mock_repo.create.assert_called_once()
        
        # 2. Embedding generated
        mock_model.encode.assert_called_with("Test vector")
        
        # 3. Added to Chroma
        mock_collection.add.assert_called_once()
        call_args = mock_collection.add.call_args[1]
        assert call_args['ids'] == [str(expected_entry.id)]
        assert call_args['documents'] == ["Test vector"]
        assert call_args['embeddings'] == [[0.1, 0.2, 0.3]]
        assert call_args['metadatas'][0]['date'] == '2025-01-01'

@pytest.mark.asyncio
async def test_search_history(mock_repo):
    """Test semantic search"""
    config = MemoryConfig(enabled=True)
    
    # Mock lazy imports
    mock_chroma = MagicMock()
    mock_sentence_transformer = MagicMock()
    
    with patch.dict(sys.modules, {
        'chromadb': mock_chroma,
        'chromadb.config': MagicMock(),
        'sentence_transformers': mock_sentence_transformer
    }):
        # Setup Mocks
        mock_collection = MagicMock()
        mock_chroma.PersistentClient.return_value.get_or_create_collection.return_value = mock_collection
        
        mock_model = MagicMock()
        mock_model.encode.return_value.tolist.return_value = [0.1, 0.1, 0.1]
        mock_sentence_transformer.SentenceTransformer.return_value = mock_model
        
        service = MemoryService(mock_repo, config)
        
        # Mock Search Results
        mock_collection.query.return_value = {
            'ids': [['id1', 'id2']],
            'documents': [['doc1', 'doc2']],
            'metadatas': [[{'date': '2025-01-01'}, {'date': '2025-01-02'}]],
            'distances': [[0.1, 0.2]]
        }
        
        # Act
        results = await service.search_history("query")
        
        # Assert
        assert len(results) == 2
        assert results[0]['id'] == 'id1'
        assert results[0]['text'] == 'doc1'
        mock_collection.query.assert_called_once()
