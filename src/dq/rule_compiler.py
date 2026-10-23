"""Run:  python -m src.dq.rule_compiler [--rule ID ...] [--all]
Block 4, Step 3: turns validated rules into VISIBLE SQL. Pure functions, no database.
A row-level rule becomes ONE predicate ('does this row pass?') that feeds
  count_sql   -> total_rows, passed_rows, failed_rows (a single row)
  failing_sql -> up to N failing rows as evidence"""

import argparse
import sys
from dataclasses import dataclass
from decimal import Decimal

from src.dq.profiler_sql import qi
from src.dq.rules_models import load_rules

SAMPLE_SIZE = 10


@dataclass(frozen=True)
class CompiledRule:
    rule_id: str
    kind: str  # "row" | "table" | "assertion"
    count_sql: str
    failing_sql: str | None


def lit(value) -> str:
    """SQL string literal (single quotes doubled)."""
    return "'" + str(value).replace("'", "''") + "'"


def num(x) -> str:
    x = float(x)
    return str(int(x)) if x.is_integer() else repr(x)


def row_predicate(rule) -> str:
    """SQL boolean that is TRUE when the row passes. Never NULL."""
    if rule.type == "NON_NULL":
        return f"{qi(rule.column)} IS NOT NULL"
    if rule.type == "UNIQUENESS":
        keys = [qi(c) for c in rule.columns]
        any_null = " OR ".join(f"{k} IS NULL" for k in keys)  # null keys are ignored
        return f"({any_null} OR count(*) OVER (PARTITION BY {', '.join(keys)}) = 1)"
    if rule.type == "ROW_CONDITION":
        return f"COALESCE(({rule.expression}), false)"
    col = qi(rule.column)
    if rule.type == "RANGE":
        parts = []
        if rule.min_value is not None:
            parts.append(
                f"{col} {'>' if rule.strict_min else '>='} {num(rule.min_value)}"
            )
        if rule.max_value is not None:
            parts.append(
                f"{col} {'<' if rule.strict_max else '<='} {num(rule.max_value)}"
            )
        core = " AND ".join(parts)
    elif rule.type == "SET":
        core = f"{col}::text IN ({', '.join(lit(v) for v in rule.values)})"
    else:  # REGEX (PostgreSQL ~ operator)
        core = f"{col}::text ~ {lit(rule.pattern)}"
    if rule.ignore_null:
        return f"({col} IS NULL OR ({core}))"
    return f"COALESCE(({core}), false)"


def compile_rule(rule, sample_size: int = SAMPLE_SIZE) -> CompiledRule:
    schema, table = rule.table.split(".")
    target = f"{qi(schema)}.{qi(table)}"

    if rule.type == "TABLE_CONDITION":
        ok = f"COALESCE(({rule.expression}), false)"
        sql = (
            f"SELECT\n  1 AS total_rows,\n"
            f"  CASE WHEN {ok} THEN 1 ELSE 0 END AS passed_rows,\n"
            f"  CASE WHEN {ok} THEN 0 ELSE 1 END AS failed_rows\n"
            f"FROM {target}"
        )
        return CompiledRule(rule.id, "table", sql, None)

    if rule.type == "SQL_ASSERTION":
        sql = (
            "SELECT total_rows, GREATEST(total_rows - failed_rows, 0) AS passed_rows, failed_rows\n"
            "FROM (\n"
            f"  SELECT (SELECT count(*) FROM {target}) AS total_rows,\n"
            f"         (SELECT count(*) FROM ({rule.sql}) AS violations) AS failed_rows\n"
            ") AS counts"
        )
        failing = f"SELECT * FROM ({rule.sql}) AS violations LIMIT {sample_size}"
        return CompiledRule(rule.id, "assertion", sql, failing)

    pred = row_predicate(rule)
    count_sql = (
        "SELECT\n  count(*) AS total_rows,\n"
        "  count(*) FILTER (WHERE is_ok) AS passed_rows,\n"
        "  count(*) FILTER (WHERE NOT is_ok) AS failed_rows\n"
        f"FROM (\n  SELECT {pred} AS is_ok\n  FROM {target}\n) AS judged"
    )
    failing_sql = (
        "SELECT * FROM (\n"
        f"  SELECT t.*, {pred} AS _dq_ok\n  FROM {target} AS t\n"
        f") AS judged\nWHERE NOT _dq_ok\nLIMIT {sample_size}"
    )
    return CompiledRule(rule.id, "row", count_sql, failing_sql)


def judge(rule, total: int, passed: int, failed: int) -> tuple[float, bool]:
    """(pass_pct, passed) from the counts. Exact Decimal maths for the threshold test."""
    if rule.type == "TABLE_CONDITION":
        return (100.0 if passed == 1 else 0.0), passed == 1
    pct = 100.0 if not total else float(Decimal(passed) * 100 / Decimal(total))
    if rule.type == "SQL_ASSERTION":
        return round(pct, 4), failed == 0
    ok = Decimal(passed) * 100 >= Decimal(str(rule.threshold)) * Decimal(total)
    return round(pct, 4), bool(ok)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Show the SQL compiled from the DQ rules."
    )
    parser.add_argument(
        "--rule", nargs="*", default=[], help="print the full SQL of these rule ids"
    )
    parser.add_argument(
        "--all", action="store_true", help="print the full SQL of every rule"
    )
    args = parser.parse_args()

    rules = load_rules()
    compiled = {r.id: compile_rule(r) for r in rules}
    print(f"{'rule id':<34}{'type':<17}{'kind':<11}{'sql lines':>10}")
    print("-" * 72)
    for r in rules:
        c = compiled[r.id]
        lines = c.count_sql.count("\n") + 1
        print(f"{r.id:<34}{r.type:<17}{c.kind:<11}{lines:>10}")
    print("-" * 72)
    print(f"{len(compiled)} rules compiled")

    unknown = set(args.rule) - set(compiled)
    if unknown:
        print("Unknown rule ids:", ", ".join(sorted(unknown)))
        return 1
    for r in rules:
        if args.all or r.id in args.rule:
            c = compiled[r.id]
            print(f"\n=== {r.id}  ({r.type}, min {r.threshold:g}%) ===")
            print("-- COUNT SQL\n" + c.count_sql)
            print(
                "-- FAILING ROWS SQL\n"
                + (c.failing_sql or "(none: a table-level rule)")
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
