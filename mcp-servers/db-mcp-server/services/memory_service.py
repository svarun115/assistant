import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import date

from config import MemoryConfig
from models import JournalEntry, JournalEntryCreate
from repositories import JournalRepository

logger = logging.getLogger(__name__)


class MemoryService:
    """
    Semantic search and journal entry logging via pgvector on Azure PostgreSQL.

    Embeddings are stored in journal_entries.embedding (vector(384)).
    Requires the pgvector extension and the add_pgvector_embeddings migration.
    """

    def __init__(self, journal_repo: JournalRepository, db, config: MemoryConfig):
        self.repo = journal_repo
        self.db = db
        self.config = config
        self.embedding_model = None
        self._model_ready = False

        if self.config.enabled:
            # Defer model loading to a background asyncio task so it doesn't
            # block the server startup event. The model takes ~30s to load;
            # keeping it synchronous in __init__ delays port binding, creating
            # a race condition where the server manager can steal the port.
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._init_embedding_model_async())
                else:
                    # Fallback: load synchronously if no event loop (e.g. tests)
                    self._init_embedding_model_sync()
            except RuntimeError:
                self._init_embedding_model_sync()

    def _init_embedding_model_sync(self):
        """Synchronous model load — used in non-async contexts (tests, fallback)."""
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {self.config.embedding_model}")
            self.embedding_model = SentenceTransformer(self.config.embedding_model)
            self._model_ready = True
            logger.info("Memory Service (pgvector) initialized successfully")
        except ImportError as e:
            logger.error(f"sentence-transformers not available: {e}")
            logger.warning("Memory Service running in DB-only mode")
            self.config.enabled = False
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            self.config.enabled = False

    async def _init_embedding_model_async(self):
        """Async background task: load model without blocking server startup."""
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {self.config.embedding_model}")
            # Run in thread pool to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            self.embedding_model = await loop.run_in_executor(
                None, lambda: SentenceTransformer(self.config.embedding_model)
            )
            self._model_ready = True
            logger.info("Memory Service (pgvector) initialized successfully")
        except ImportError as e:
            logger.error(f"sentence-transformers not available: {e}")
            logger.warning("Memory Service running in DB-only mode")
            self.config.enabled = False
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            self.config.enabled = False

    def _generate_embedding(self, text: str) -> List[float]:
        if not self.embedding_model:
            return []
        return self.embedding_model.encode(text).tolist()

    async def log_entry(self, entry_data: JournalEntryCreate) -> JournalEntry:
        """
        Create a journal entry in PostgreSQL and store its embedding in the same row.
        """
        entry = await self.repo.create(entry_data)

        if self.config.enabled and self.embedding_model:
            try:
                embedding = self._generate_embedding(entry.raw_text)
                await self.db.execute(
                    "UPDATE journal_entries SET embedding = $1 WHERE id = $2",
                    embedding, entry.id
                )
                logger.info(f"Indexed entry {entry.id} in pgvector")
            except Exception as e:
                logger.error(f"Failed to index entry {entry.id}: {e}")
                # Don't fail the request if vector indexing fails

        return entry

    async def search_history(
        self,
        query: str,
        limit: int = 5,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        entry_types: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search over journal history using pgvector cosine distance.
        Filters are applied in SQL — no post-filtering overhead.
        """
        if not self.config.enabled or not self.embedding_model:
            logger.warning("Vector search requested but Memory Service is disabled")
            return []

        try:
            query_embedding = self._generate_embedding(query)

            # Build WHERE clauses dynamically
            conditions = ["is_deleted = FALSE", "embedding IS NOT NULL"]
            params: list = [query_embedding, limit]
            param_idx = 3  # $1=embedding, $2=limit, next is $3

            if start_date:
                conditions.append(f"entry_date >= ${param_idx}")
                params.append(start_date)
                param_idx += 1

            if end_date:
                conditions.append(f"entry_date <= ${param_idx}")
                params.append(end_date)
                param_idx += 1

            if entry_types:
                conditions.append(f"entry_type = ANY(${param_idx})")
                params.append(entry_types)
                param_idx += 1

            if tags:
                # tags is TEXT[] in PostgreSQL; match entries that share at least one tag
                conditions.append(f"tags && ${param_idx}")
                params.append(tags)
                param_idx += 1

            where_sql = " AND ".join(conditions)

            rows = await self.db.fetch(
                f"""
                SELECT id, raw_text, entry_date, entry_type, tags, created_at,
                       embedding <=> $1 AS distance
                FROM journal_entries
                WHERE {where_sql}
                ORDER BY embedding <=> $1
                LIMIT $2
                """,
                *params,
            )

            results = []
            for row in rows:
                results.append({
                    "id": str(row["id"]),
                    "text": row["raw_text"],
                    "metadata": {
                        "date": str(row["entry_date"]),
                        "type": row["entry_type"],
                        "tags": ",".join(row["tags"]) if row["tags"] else "",
                    },
                    "score": float(row["distance"]),
                })

            logger.info(
                f"Search returned {len(results)} results "
                f"(filters: dates={bool(start_date or end_date)}, "
                f"types={bool(entry_types)}, tags={bool(tags)})"
            )
            return results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    async def get_entries_by_date(self, entry_date: date) -> List[JournalEntry]:
        """Get entries for a specific date (DB only)"""
        return await self.repo.get_by_date(entry_date)
