"""Generate the Markdown DQ report for one source from stored profiles and scan results.

python -m src.dq.report [--source olist] [--out reports/dq_report_olist.md]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import text

from config.settings import PROJECT_ROOT
from src.common.db import get_admin_engine
from src.dq.report_md import build_report
from src.dq.score_run import load_results
from src.dq.scoring import build_scorecard

REPORT_DIR = PROJECT_ROOT / "reports"
FAILING_SQL = text("""
    SELECT r.rule_id, r.schema_name, r.table_name, r.dimension, r.rule_type,
           trim_scale(r.threshold) AS threshold, r.pass_pct, r.failed_rows, r.total_rows,
           r.column_names, r.sample_failures, r.failing_sql, ru.description
    FROM dq.latest_results r
    LEFT JOIN dq.rules ru ON ru.source_id = r.source_id AND ru.rule_id = r.rule_id
    WHERE r.source_id = :source AND r.status = 'failed'
    ORDER BY r.pass_pct, r.rule_id""")
NULLS_SQL = text("""
    SELECT schema_name, table_name, column_name, null_pct, null_count, row_count
    FROM dq.latest_profiles WHERE source_id = :source AND null_count > 0
    ORDER BY null_pct DESC, schema_name, table_name, column_name LIMIT 10""")
PROFILED_AT_SQL = text(
    "SELECT max(profiled_at) AS profiled_at FROM dq.latest_profiles WHERE source_id = :source"
)
COVERAGE_SQL = text("""
    WITH cols AS (SELECT DISTINCT schema_name, table_name, column_name
                  FROM dq.latest_profiles WHERE source_id = :source),
         ruled AS (SELECT DISTINCT schema_name, table_name, unnest(column_names) AS column_name
                   FROM dq.latest_results WHERE source_id = :source)
    SELECT (SELECT count(DISTINCT (schema_name, table_name)) FROM cols) AS tables,
           (SELECT count(*) FROM cols) AS columns,
           (SELECT count(*) FROM cols JOIN ruled USING (schema_name, table_name, column_name))
               AS columns_with_rules,
           (SELECT count(DISTINCT (r.schema_name, r.table_name)) FROM dq.latest_results r
             WHERE r.source_id = :source AND EXISTS (SELECT 1 FROM cols c
               WHERE c.schema_name = r.schema_name AND c.table_name = r.table_name))
               AS tables_with_rules""")
PROFILE_COLS_SQL = text(
    "SELECT schema_name, table_name, column_name FROM dq.latest_profiles WHERE source_id = :source"
)
RESULT_COLS_SQL = text(
    "SELECT schema_name, table_name, column_names FROM dq.latest_results WHERE source_id = :source"
)


def fetch(sql, source: str) -> list[dict]:
    with get_admin_engine().connect() as conn:
        return [dict(r) for r in conn.execute(sql, {"source": source}).mappings()]


def coverage_in_python(source: str) -> dict[str, int]:
    """Second formulation of the coverage numbers, computed in Python from the raw rows."""
    cols = {
        (r["schema_name"], r["table_name"], r["column_name"])
        for r in fetch(PROFILE_COLS_SQL, source)
    }
    tables = {(s, t) for s, t, _ in cols}
    covered: set = set()
    ruled_tables: set = set()
    for r in fetch(RESULT_COLS_SQL, source):
        table = (r["schema_name"], r["table_name"])
        if table in tables:
            ruled_tables.add(table)
        for c in r["column_names"] or []:
            if (*table, c) in cols:
                covered.add((*table, c))
    return {
        "tables": len(tables),
        "columns": len(cols),
        "columns_with_rules": len(covered),
        "tables_with_rules": len(ruled_tables),
    }


def check_report(
    report: str, card, failing: list[dict], coverage: dict, source: str
) -> list[str]:
    problems = []
    if {f["rule_id"] for f in failing} != {rid for rid, _ in card.worst_rules}:
        problems.append("failing rules in the report differ from the scorecard")
    if report.count("\n### ") != len(failing):
        problems.append("number of finding sections != number of failing rules")
    problems += [
        f"rule {f['rule_id']} missing from the report"
        for f in failing
        if f"`{f['rule_id']}`" not in report
    ]
    if f"Overall score {card.overall.score}" not in report:
        problems.append("overall score missing from the report")
    other = coverage_in_python(source)
    if {k: int(v) for k, v in coverage.items()} != other:
        problems.append(f"coverage mismatch: sql={dict(coverage)} python={other}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate the Markdown DQ report")
    ap.add_argument("--source", default="olist")
    ap.add_argument("--out", help="output file (default reports/dq_report_<source>.md)")
    args = ap.parse_args()

    results = load_results(args.source)
    if not results:
        print(
            f"No results for {args.source}. Run: python -m src.dq.runner --source {args.source}"
        )
        return 1
    card = build_scorecard(results)
    failing = fetch(FAILING_SQL, args.source)
    coverage = fetch(COVERAGE_SQL, args.source)[0]
    report = build_report(
        args.source,
        card,
        failing,
        fetch(NULLS_SQL, args.source),
        coverage,
        max(r["scanned_at"] for r in results),
        fetch(PROFILED_AT_SQL, args.source)[0]["profiled_at"],
    )
    safe = args.source.replace(":", "_")
    out = Path(args.out) if args.out else REPORT_DIR / f"dq_report_{safe}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"Wrote {out} ({len(report.splitlines())} lines)")

    problems = check_report(report, card, failing, coverage, args.source)
    print(f"Report self-check: {len(problems)} problems")
    for p in problems:
        print("  ", p)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
