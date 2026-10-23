"""Run:  python -m src.dq.runner [--source olist] [--rules ID ...] [--rules-dir PATH] [--timeout 120]
Block 4, Step 4: executes the compiled DQ rules and stores verdicts + evidence in dq.results.
Rule SQL runs as the READ-ONLY t2s_reader; results are written by the admin engine.
A rule whose SQL fails is stored with status='error' and the scan continues."""

import argparse
import json
import sys
import time
from pathlib import Path

from sqlalchemy import text

from src.common.db import get_admin_engine, get_reader_engine
from src.common.logging import get_logger
from src.dq.profiler import run_generated
from src.dq.rule_compiler import compile_rule, judge
from src.dq.rules_models import RULES_DIR, RuleFileError, columns_of, load_rules

log = get_logger("dq_runner")

UPSERT_RULE = text(
    "INSERT INTO dq.rules (source_id, rule_id, schema_name, table_name, column_names, "
    "rule_type, dimension, threshold, description, definition, enabled) VALUES "
    "(:source_id, :rule_id, :schema_name, :table_name, CAST(:column_names AS text[]), "
    ":rule_type, :dimension, :threshold, :description, CAST(:definition AS jsonb), :enabled) "
    "ON CONFLICT (source_id, rule_id) DO UPDATE SET schema_name = EXCLUDED.schema_name, "
    "table_name = EXCLUDED.table_name, column_names = EXCLUDED.column_names, "
    "rule_type = EXCLUDED.rule_type, dimension = EXCLUDED.dimension, "
    "threshold = EXCLUDED.threshold, description = EXCLUDED.description, "
    "definition = EXCLUDED.definition, enabled = EXCLUDED.enabled, updated_at = now()"
)
START_RUN = text(
    "INSERT INTO dq.scan_runs (source_id) VALUES (:source_id) RETURNING run_id"
)
FINISH_RUN = text(
    "UPDATE dq.scan_runs SET status = 'completed', finished_at = now(), rules_total = :t, "
    "rules_passed = :p, rules_failed = :f, rules_errored = :e WHERE run_id = CAST(:run_id AS uuid)"
)
FAIL_RUN = text(
    "UPDATE dq.scan_runs SET status = 'failed', finished_at = now(), notes = :notes "
    "WHERE run_id = CAST(:run_id AS uuid)"
)
INSERT_RESULT = text(
    "INSERT INTO dq.results (run_id, source_id, rule_id, schema_name, table_name, column_names, "
    "rule_type, dimension, threshold, total_rows, passed_rows, failed_rows, pass_pct, passed, "
    "status, sql_used, failing_sql, sample_failures, error_message, elapsed_ms) VALUES "
    "(CAST(:run_id AS uuid), :source_id, :rule_id, :schema_name, :table_name, "
    "CAST(:column_names AS text[]), :rule_type, :dimension, :threshold, :total_rows, "
    ":passed_rows, :failed_rows, :pass_pct, :passed, :status, :sql_used, :failing_sql, "
    "CAST(:sample_failures AS jsonb), :error_message, :elapsed_ms)"
)


def rule_params(r) -> dict:
    return {
        "source_id": r.source_id,
        "rule_id": r.id,
        "schema_name": r.table.split(".")[0],
        "table_name": r.table.split(".")[1],
        "column_names": columns_of(r) or None,
        "rule_type": r.type,
        "dimension": r.dimension,
        "threshold": r.threshold,
        "description": r.description,
        "definition": r.model_dump_json(),
        "enabled": r.enabled,
    }


def execute_rule(reader, rule, timeout_s: int) -> dict:
    """Run ONE rule as t2s_reader. Never raises for a bad rule: returns status='error'."""
    compiled = compile_rule(rule)
    schema, table = rule.table.split(".")
    res = {
        "source_id": rule.source_id,
        "rule_id": rule.id,
        "schema_name": schema,
        "table_name": table,
        "column_names": columns_of(rule) or None,
        "rule_type": rule.type,
        "dimension": rule.dimension,
        "threshold": rule.threshold,
        "total_rows": None,
        "passed_rows": None,
        "failed_rows": None,
        "pass_pct": None,
        "passed": False,
        "status": "error",
        "sql_used": compiled.count_sql,
        "failing_sql": compiled.failing_sql,
        "sample_failures": None,
        "error_message": None,
        "elapsed_ms": None,
    }
    started = time.perf_counter()
    try:
        with (
            reader.connect() as conn
        ):  # read-only role; rolled back when the block ends
            conn.exec_driver_sql(f"SET LOCAL statement_timeout = '{int(timeout_s)}s'")
            total, passed, failed = (
                int(x) for x in run_generated(conn, compiled.count_sql).one()
            )
            if failed > 0 and compiled.failing_sql:
                rows = run_generated(conn, compiled.failing_sql)
                cols = list(rows.keys())
                samples = [
                    {k: v for k, v in zip(cols, row) if k != "_dq_ok"}
                    for row in rows.all()
                ]
                res["sample_failures"] = json.dumps(samples, default=str)
        pct, ok = judge(rule, total, passed, failed)
        res.update(
            total_rows=total,
            passed_rows=passed,
            failed_rows=failed,
            pass_pct=pct,
            passed=ok,
            status="passed" if ok else "failed",
        )
    except Exception as exc:  # a bad rule must not stop the scan
        detail = str(getattr(exc, "orig", exc)).strip().splitlines()
        res["error_message"] = (detail[0] if detail else type(exc).__name__)[:500]
    res["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return res


def print_report(results: list[dict]) -> None:
    print(
        f"\n{'rule id':<36}{'status':<8}{'rows':>10}{'failed':>9}{'pass %':>10}{'min %':>7}{'ms':>9}"
    )
    print("-" * 89)
    for r in results:
        rows = f"{r['total_rows']:,}" if r["total_rows"] is not None else "-"
        failed = f"{r['failed_rows']:,}" if r["failed_rows"] is not None else "-"
        pct = f"{r['pass_pct']:.4f}" if r["pass_pct"] is not None else "-"
        print(
            f"{r['rule_id']:<36}{r['status'].upper():<8}{rows:>10}{failed:>9}{pct:>10}"
            f"{float(r['threshold']):>7g}{r['elapsed_ms']:>9.0f}"
        )
    print("-" * 89)
    for r in results:
        if r["status"] == "error":
            print(f"\nERROR in {r['rule_id']}: {r['error_message']}")
        elif r["status"] == "failed" and r["sample_failures"]:
            print(
                f"\nFAILED {r['rule_id']}: sample failing rows (up to 2 of 10 stored)"
            )
            for row in json.loads(r["sample_failures"])[:2]:
                print("  ", json.dumps(row, default=str)[:140])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute DQ rules and store the results."
    )
    parser.add_argument("--source", default="olist")
    parser.add_argument("--rules", nargs="*", default=[], help="only these rule ids")
    parser.add_argument("--rules-dir", default=str(RULES_DIR))
    parser.add_argument("--timeout", type=int, default=120, help="seconds per rule")
    args = parser.parse_args()

    try:
        all_rules = load_rules(Path(args.rules_dir))
    except RuleFileError as err:
        print("Rule files have problems:")
        for p in err.problems:
            print("  -", p)
        return 1
    rules = [r for r in all_rules if r.source_id == args.source]
    if not rules:
        print(f"No rules for source {args.source!r} in {args.rules_dir}")
        return 1
    unknown = set(args.rules) - {r.id for r in rules}
    if unknown:
        print("Unknown rule ids:", ", ".join(sorted(unknown)))
        return 1
    to_run = [r for r in rules if r.enabled and (not args.rules or r.id in args.rules)]

    admin, reader = get_admin_engine(), get_reader_engine()
    with admin.begin() as conn:  # transaction 1: sync rules, register the scan, commit
        for r in rules:
            conn.execute(UPSERT_RULE, rule_params(r))
        run_id = str(conn.execute(START_RUN, {"source_id": args.source}).scalar_one())
    log.info(
        "Scan %s started: source=%s, %d rules to run", run_id, args.source, len(to_run)
    )

    try:
        results = [execute_rule(reader, r, args.timeout) for r in to_run]
        counts = {
            s: sum(1 for x in results if x["status"] == s)
            for s in ("passed", "failed", "error")
        }
        with (
            admin.begin() as conn
        ):  # transaction 2: all results + 'completed', all or nothing
            if results:
                conn.execute(INSERT_RESULT, [{"run_id": run_id, **r} for r in results])
            conn.execute(
                FINISH_RUN,
                {
                    "run_id": run_id,
                    "t": len(results),
                    "p": counts["passed"],
                    "f": counts["failed"],
                    "e": counts["error"],
                },
            )
    except BaseException as exc:  # includes Ctrl+C: the scan must never stay 'running'
        message = str(exc).strip()
        with admin.begin() as conn:
            conn.execute(FAIL_RUN, {"run_id": run_id, "notes": message[:500]})
        log.error(
            "Scan %s FAILED: %s",
            run_id,
            message.splitlines()[0] if message else type(exc).__name__,
        )
        raise

    print_report(results)
    print(
        f"\nScan {run_id} completed: {counts['passed']} passed, "
        f"{counts['failed']} failed, {counts['error']} errors."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
