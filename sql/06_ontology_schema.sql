-- sql/06_ontology_schema.sql: Business Ontology concepts and metrics

CREATE TABLE IF NOT EXISTS meta.ontology_terms (
    term_id          TEXT PRIMARY KEY,
    source_id        TEXT NOT NULL,
    term_name        TEXT NOT NULL,
    term_type        TEXT NOT NULL CHECK (term_type IN ('metric', 'concept', 'dimension')),
    definition       TEXT NOT NULL,
    sql_expression   TEXT NOT NULL,
    base_table       TEXT NOT NULL,
    mapped_columns   TEXT[] NOT NULL DEFAULT '{}'::text[],
    synonyms         TEXT[] NOT NULL DEFAULT '{}'::text[],
    status           TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'rejected')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX IF NOT EXISTS idx_ontology_source_type 
    ON meta.ontology_terms (source_id, term_type);
CREATE INDEX IF NOT EXISTS idx_ontology_source_status 
    ON meta.ontology_terms (source_id, status);