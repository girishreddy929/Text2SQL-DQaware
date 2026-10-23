-- sql/03_dq_rules_schema.sql   (Block 4, Step 2)
-- Rule definitions, scan runs and results. Safe to re-run (IF NOT EXISTS / OR REPLACE).

CREATE SCHEMA IF NOT EXISTS dq;

-- Synced from config/dq_rules/*.yaml on every scan. The YAML stays the source of truth.
CREATE TABLE IF NOT EXISTS dq.rules (
    source_id     text         NOT NULL,
    rule_id       text         NOT NULL,
    schema_name   text         NOT NULL,
    table_name    text         NOT NULL,
    column_names  text[],
    rule_type     text         NOT NULL
                  CHECK (rule_type IN ('NON_NULL', 'UNIQUENESS', 'RANGE', 'SET', 'REGEX',
                                       'ROW_CONDITION', 'TABLE_CONDITION', 'SQL_ASSERTION')),
    dimension     text         NOT NULL
                  CHECK (dimension IN ('Completeness', 'Uniqueness', 'Validity',
                                       'Consistency', 'Timeliness', 'Accuracy')),
    threshold     numeric(5,2) NOT NULL CHECK (threshold BETWEEN 0 AND 100),
    description   text         NOT NULL DEFAULT '',
    definition    jsonb        NOT NULL,   -- the full validated rule as JSON
    enabled       boolean      NOT NULL DEFAULT true,
    updated_at    timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, rule_id)
);

-- One row per scan (a dated inspection visit).
CREATE TABLE IF NOT EXISTS dq.scan_runs (
    run_id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       text        NOT NULL,
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    status          text        NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'completed', 'failed')),
    rules_total     integer     NOT NULL DEFAULT 0,
    rules_passed    integer     NOT NULL DEFAULT 0,
    rules_failed    integer     NOT NULL DEFAULT 0,
    rules_errored   integer     NOT NULL DEFAULT 0,
    notes           text
);

-- One row per rule per scan: the verdict plus the evidence.
CREATE TABLE IF NOT EXISTS dq.results (
    run_id           uuid         NOT NULL REFERENCES dq.scan_runs (run_id) ON DELETE CASCADE,
    source_id        text         NOT NULL,
    rule_id          text         NOT NULL,
    schema_name      text         NOT NULL,
    table_name       text         NOT NULL,
    column_names     text[],
    rule_type        text         NOT NULL,
    dimension        text         NOT NULL,
    threshold        numeric(5,2) NOT NULL,   -- threshold in force when the scan ran
    total_rows       bigint,                  -- rows judged (TABLE_CONDITION counts as 1)
    passed_rows      bigint,
    failed_rows      bigint,                  -- SQL_ASSERTION: rows returned by the query
    pass_pct         numeric(7,4),
    passed           boolean      NOT NULL,
    status           text         NOT NULL CHECK (status IN ('passed', 'failed', 'error')),
    sql_used         text         NOT NULL DEFAULT '',   -- the exact SQL that produced the counts
    failing_sql      text,                               -- SQL that lists the failing rows
    sample_failures  jsonb,                              -- up to 10 failing rows as JSON
    error_message    text,
    elapsed_ms       double precision,
    PRIMARY KEY (run_id, rule_id),
    CHECK (status = 'error' OR (total_rows IS NOT NULL AND failed_rows IS NOT NULL)),
    CHECK (failed_rows IS NULL OR failed_rows >= 0)
);

CREATE INDEX IF NOT EXISTS idx_results_rule ON dq.results (source_id, rule_id);

-- Newest COMPLETED verdict per rule. Dashboards and the DQ Advisor read this view.
CREATE OR REPLACE VIEW dq.latest_results AS
SELECT DISTINCT ON (r.source_id, r.rule_id)
       r.*,
       s.started_at AS scanned_at
FROM dq.results r
JOIN dq.scan_runs s ON s.run_id = r.run_id
WHERE s.status = 'completed'
ORDER BY r.source_id, r.rule_id, s.started_at DESC;

COMMENT ON TABLE dq.rules       IS 'Rule definitions synced from config/dq_rules/*.yaml.';
COMMENT ON TABLE dq.scan_runs   IS 'One row per rule scan (a dated inspection).';
COMMENT ON TABLE dq.results     IS 'One row per rule per scan: counts, verdict, exact SQL, sample failing rows.';
COMMENT ON VIEW  dq.latest_results IS 'Newest completed verdict per rule.';