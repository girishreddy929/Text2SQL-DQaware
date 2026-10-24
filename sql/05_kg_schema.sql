-- sql/05_kg_schema.sql: Knowledge Graph nodes and edges

CREATE TABLE IF NOT EXISTS meta.kg_nodes (
    node_id      TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL,
    node_type    TEXT NOT NULL,
    name         TEXT NOT NULL,
    properties   JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_kg_nodes_source_type 
    ON meta.kg_nodes (source_id, node_type);

CREATE TABLE IF NOT EXISTS meta.kg_edges (
    edge_id      TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL,
    edge_type    TEXT NOT NULL,
    src_node_id  TEXT NOT NULL REFERENCES meta.kg_nodes(node_id) ON DELETE CASCADE,
    tgt_node_id  TEXT NOT NULL REFERENCES meta.kg_nodes(node_id) ON DELETE CASCADE,
    weight       NUMERIC(5, 4) NOT NULL DEFAULT 1.0,
    properties   JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_kg_edges_source_type 
    ON meta.kg_edges (source_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_kg_edges_src 
    ON meta.kg_edges (src_node_id);
CREATE INDEX IF NOT EXISTS idx_kg_edges_tgt 
    ON meta.kg_edges (tgt_node_id);