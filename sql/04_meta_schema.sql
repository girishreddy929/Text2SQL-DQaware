-- Block 8: metadata layer (hand-written, idempotent). Applied by src/metadata/init_schema.py
CREATE SCHEMA IF NOT EXISTS meta;

CREATE TABLE IF NOT EXISTS meta.generation_runs (
    run_id          uuid PRIMARY KEY,
    source_id       text NOT NULL,
    model           text NOT NULL,
    prompt_version  text NOT NULL,
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    status          text NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'completed', 'failed')),
    tables_done     integer NOT NULL DEFAULT 0,
    columns_done    integer NOT NULL DEFAULT 0,
    notes           text
);

CREATE TABLE IF NOT EXISTS meta.tables (
    source_id     text NOT NULL,
    schema_name   text NOT NULL,
    table_name    text NOT NULL,
    description   text NOT NULL,
    synonyms      text[] NOT NULL DEFAULT '{}',
    status        text NOT NULL DEFAULT 'draft'
                  CHECK (status IN ('draft', 'approved', 'rejected')),
    generated_by  text,
    run_id        uuid REFERENCES meta.generation_runs (run_id),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    reviewed_by   text,
    reviewed_at   timestamptz,
    PRIMARY KEY (source_id, schema_name, table_name)
);

CREATE TABLE IF NOT EXISTS meta.columns (
    source_id         text NOT NULL,
    schema_name       text NOT NULL,
    table_name        text NOT NULL,
    column_name       text NOT NULL,
    data_type         text,
    ordinal_position  integer,
    description       text NOT NULL,
    synonyms          text[] NOT NULL DEFAULT '{}',
    column_role       text,           -- identifier | measure | category | date | flag | free_text
    is_pii            boolean NOT NULL DEFAULT false,
    pii_reason        text,
    status            text NOT NULL DEFAULT 'draft'
                      CHECK (status IN ('draft', 'approved', 'rejected')),
    generated_by      text,
    run_id            uuid REFERENCES meta.generation_runs (run_id),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    reviewed_by       text,
    reviewed_at       timestamptz,
    PRIMARY KEY (source_id, schema_name, table_name, column_name)
);

-- BIRD's human-written descriptions (reference for scoring; also usable as hints)
CREATE TABLE IF NOT EXISTS meta.reference_descriptions (
    source_id          text NOT NULL,
    schema_name        text NOT NULL,
    table_name         text NOT NULL,
    column_name        text NOT NULL,
    human_name         text,
    description        text,
    data_format        text,
    value_description  text,
    loaded_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, schema_name, table_name, column_name)
);

-- Similarity of our generated descriptions to the reference (one score run = many rows)
CREATE TABLE IF NOT EXISTS meta.description_scores (
    score_run_id     uuid NOT NULL,
    source_id        text NOT NULL,
    schema_name      text NOT NULL,
    table_name       text NOT NULL,
    column_name      text NOT NULL,
    generated_text   text NOT NULL,
    reference_text   text NOT NULL,
    similarity       numeric(7,4) NOT NULL,
    embedding_model  text NOT NULL,
    scored_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (score_run_id, schema_name, table_name, column_name)
);

CREATE INDEX IF NOT EXISTS meta_columns_status_idx ON meta.columns (source_id, status);