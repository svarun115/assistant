-- Phase 0: Migrate from ChromaDB to pgvector
-- Adds vector embedding column to journal_entries for cloud-hosted semantic search.
-- Eliminates ChromaDB (local-only) dependency.
--
-- Prerequisites: Azure PostgreSQL Flexible Server (pgvector pre-installed)
-- Embedding dimensions: 384 (sentence-transformers/all-MiniLM-L6-v2)

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE journal_entries ADD COLUMN IF NOT EXISTS embedding vector(384);

-- IVFFlat index for approximate nearest neighbour cosine search.
-- lists=100 is appropriate for up to ~1M rows.
CREATE INDEX IF NOT EXISTS idx_journal_entries_embedding
    ON journal_entries
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
