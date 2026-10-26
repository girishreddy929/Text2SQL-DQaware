-- sql/08_app_schema.sql
CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE IF NOT EXISTS app.semantic_cache (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id text NOT NULL,
    question text NOT NULL,
    generated_sql text NOT NULL,
    tables_used text[] NOT NULL,
    embedding vector(768),
    feedback_score int DEFAULT 0,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS semantic_cache_embedding_idx 
ON app.semantic_cache USING hnsw (embedding vector_cosine_ops);