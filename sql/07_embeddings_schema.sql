-- sql/07_embeddings_schema.sql: Vector storage for schema and ontology elements

CREATE TABLE IF NOT EXISTS meta.schema_embeddings (
    id           TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL,
    entity_type  TEXT NOT NULL CHECK (entity_type IN ('table', 'column', 'metric', 'business_term')),
    entity_name  TEXT NOT NULL,
    content      TEXT NOT NULL,
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding    VECTOR(768) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_schema_embeddings_source_type 
    ON meta.schema_embeddings (source_id, entity_type);

CREATE INDEX IF NOT EXISTS idx_schema_embeddings_hnsw 
    ON meta.schema_embeddings USING hnsw (embedding vector_cosine_ops);