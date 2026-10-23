-- sql/02_dq_schema.sql   (Block 3, Step 2)
-- Profiling tables. Safe to re-run: everything uses IF NOT EXISTS / OR REPLACE.
-- Later DQ blocks add their own files (rules, results, scores) to the same dq schema.

CREATE SCHEMA IF NOT EXISTS dq;
COMMENT ON SCHEMA dq IS 'Data quality: profiles, rules, scan runs, results, scores (TrustSQL DQCA engine)';

-- One row per profiler run (a dated snapshot).
CREATE TABLE IF NOT EXISTS dq.profile_runs (
    run_id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id         text        NOT NULL,
    schemas           text[]      NOT NULL,
    started_at        timestamptz NOT NULL DEFAULT now(),
    finished_at       timestamptz,
    status            text        NOT NULL DEFAULT 'running'
                      CHECK (status IN ('running', 'completed', 'failed')),
    tables_profiled   integer     NOT NULL DEFAULT 0,
    columns_profiled  integer     NOT NULL DEFAULT 0,
    notes             text
);

-- One row per table per run: row count plus the exact SQL that produced the statistics.
CREATE TABLE IF NOT EXISTS dq.profile_tables (
    run_id        uuid        NOT NULL REFERENCES dq.profile_runs (run_id) ON DELETE CASCADE,
    source_id     text        NOT NULL,
    schema_name   text        NOT NULL,
    table_name    text        NOT NULL,
    row_count     bigint      NOT NULL,
    column_count  integer     NOT NULL,
    stats_sql     text        NOT NULL,
    elapsed_ms    double precision,
    PRIMARY KEY (run_id, schema_name, table_name)
);

-- One row per column per run.
CREATE TABLE IF NOT EXISTS dq.profiles (
    run_id            uuid         NOT NULL,
    source_id         text         NOT NULL,
    schema_name       text         NOT NULL,
    table_name        text         NOT NULL,
    column_name       text         NOT NULL,
    ordinal_position  integer      NOT NULL,
    data_type         text         NOT NULL,
    type_category     text         NOT NULL
                      CHECK (type_category IN ('numeric', 'text', 'temporal', 'boolean', 'other')),
    row_count         bigint       NOT NULL,
    null_count        bigint       NOT NULL,
    null_pct          numeric(7,4) NOT NULL,
    distinct_count    bigint,
    distinct_pct      numeric(7,4),   -- distinct values as % of NON-NULL values (100 = all unique)
    min_value         text,           -- stored as text so one column fits every data type
    max_value         text,
    mean_value        double precision,   -- numeric columns only
    stddev_value      double precision,   -- numeric columns only
    min_length        integer,            -- text columns only
    max_length        integer,
    avg_length        double precision,
    top_values        jsonb,              -- [{"value": "...", "count": 123, "pct": 12.3}, ...]
    top_values_sql    text,               -- exact SQL used for top_values (NULL if skipped)
    PRIMARY KEY (run_id, schema_name, table_name, column_name),
    FOREIGN KEY (run_id, schema_name, table_name)
        REFERENCES dq.profile_tables (run_id, schema_name, table_name) ON DELETE CASCADE,
    CHECK (null_count BETWEEN 0 AND row_count)
);

CREATE INDEX IF NOT EXISTS idx_profiles_lookup
    ON dq.profiles (source_id, schema_name, table_name, column_name);

-- Newest COMPLETED profile per column. Downstream blocks read this view.
CREATE OR REPLACE VIEW dq.latest_profiles AS
SELECT DISTINCT ON (p.source_id, p.schema_name, p.table_name, p.column_name)
       p.*,
       r.started_at AS profiled_at
FROM dq.profiles p
JOIN dq.profile_runs r ON r.run_id = p.run_id
WHERE r.status = 'completed'
ORDER BY p.source_id, p.schema_name, p.table_name, p.column_name, r.started_at DESC;

COMMENT ON TABLE dq.profile_runs   IS 'One row per profiler run (a dated snapshot).';
COMMENT ON TABLE dq.profile_tables IS 'Per table per run: row count and the exact stats SQL used.';
COMMENT ON TABLE dq.profiles       IS 'Per column per run: null %, distinct, min/max/mean, lengths, top values.';
COMMENT ON VIEW  dq.latest_profiles IS 'Newest completed profile per column.';