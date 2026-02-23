"""
One-time migration: ChromaDB → pgvector

Copies existing embeddings from local ChromaDB into journal_entries.embedding
on Azure PostgreSQL. For entries missing from ChromaDB, re-embeds from raw_text.

Run once after applying migrations/add_pgvector_embeddings.sql:
    APP_ENV=production python migrate_chroma_to_pgvector.py
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main():
    # Load production environment
    from config import DatabaseConfig, MemoryConfig, load_app_environment
    load_app_environment()

    db_config = DatabaseConfig.from_environment()
    mem_config = MemoryConfig.from_environment()

    # --- Connect to Azure PostgreSQL ---
    import asyncpg
    from pgvector.asyncpg import register_vector

    logger.info(f"Connecting to {db_config.host}:{db_config.port}/{db_config.database}...")
    ssl = True if db_config.ssl_mode == "require" else "prefer"

    async def _init_conn(conn):
        await register_vector(conn)

    pool = await asyncpg.create_pool(
        host=db_config.host, port=db_config.port,
        database=db_config.database,
        user=db_config.user, password=db_config.password,
        ssl=ssl, min_size=1, max_size=5,
        init=_init_conn,
    )
    logger.info("Connected.")

    # --- Load embedding model ---
    from sentence_transformers import SentenceTransformer
    logger.info(f"Loading embedding model: {mem_config.embedding_model}")
    model = SentenceTransformer(mem_config.embedding_model)

    # --- Open ChromaDB ---
    chroma_path = os.getenv("CHROMA_PATH")
    if not chroma_path:
        # Production default on Windows
        base = os.getenv("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
        chroma_path = str(Path(base) / "JournalMCP" / "chroma_db")

    logger.info(f"Opening ChromaDB at {chroma_path}")
    try:
        import chromadb
        chroma_client = chromadb.PersistentClient(path=chroma_path)
        collection = chroma_client.get_collection("journal_memories")
        count = collection.count()
        logger.info(f"ChromaDB collection has {count} entries")
    except Exception as e:
        logger.warning(f"Could not open ChromaDB: {e}")
        logger.info("Will re-embed all journal entries from raw_text instead.")
        collection = None
        count = 0

    # --- Build UUID → embedding map from ChromaDB ---
    chroma_embeddings: dict = {}
    if collection and count > 0:
        # Fetch all in one call (164 KB, safe to load entirely)
        result = collection.get(include=["embeddings"])
        for doc_id, embedding in zip(result["ids"], result["embeddings"]):
            chroma_embeddings[doc_id] = embedding
        logger.info(f"Loaded {len(chroma_embeddings)} embeddings from ChromaDB")

    # --- Fetch all active journal entries that need embeddings ---
    rows = await pool.fetch(
        "SELECT id, raw_text FROM journal_entries WHERE is_deleted = FALSE ORDER BY entry_date"
    )
    logger.info(f"Found {len(rows)} active journal entries in PostgreSQL")

    matched = 0
    reembedded = 0
    skipped = 0

    for row in rows:
        entry_id = str(row["id"])
        raw_text = row["raw_text"]

        if entry_id in chroma_embeddings:
            embedding = chroma_embeddings[entry_id]
            matched += 1
        else:
            # Not in ChromaDB — generate fresh embedding
            try:
                embedding = model.encode(raw_text).tolist()
                reembedded += 1
            except Exception as e:
                logger.error(f"  Failed to embed entry {entry_id}: {e}")
                skipped += 1
                continue

        try:
            await pool.execute(
                "UPDATE journal_entries SET embedding = $1 WHERE id = $2",
                embedding, row["id"]
            )
        except Exception as e:
            logger.error(f"  Failed to write embedding for {entry_id}: {e}")
            skipped += 1

    await pool.close()

    # --- Summary ---
    logger.info("")
    logger.info("=== Migration complete ===")
    logger.info(f"  Copied from ChromaDB : {matched}")
    logger.info(f"  Re-embedded from text: {reembedded}")
    logger.info(f"  Skipped (errors)     : {skipped}")
    logger.info(f"  Total processed      : {matched + reembedded + skipped} / {len(rows)}")

    if skipped > 0:
        logger.warning(f"{skipped} entries were skipped due to errors — run again to retry.")
    else:
        logger.info("All entries indexed. ChromaDB is no longer needed.")


if __name__ == "__main__":
    asyncio.run(main())
