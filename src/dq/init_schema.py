"""Run:  python -m src.dq.init_schema [--reset] [--reset-rules]
Creates the dq tables from sql/02_dq_schema.sql (profiling) and sql/03_dq_rules_schema.sql
(rules, scan runs, results) in ONE transaction. Safe to re-run.
--reset        first drops ONLY the profiling objects (all profile data is lost)
--reset-rules  first drops ONLY the rule objects (rules, scan runs, results are lost)
Uses the admin engine; the read-only agent role gets no access to dq."""

import argparse
import sys

from sqlalchemy import text

from config.settings import PROJECT_ROOT
from src.common.db import get_admin_engine
from src.common.logging import get_logger

log = get_logger("dq_init")

SQL_FILES = [
    PROJECT_ROOT / "sql" / "02_dq_schema.sql",
    PROJECT_ROOT / "sql" / "03_dq_rules_schema.sql",
]
RESET_PROFILING_SQL = """
DROP VIEW  IF EXISTS dq.latest_profiles;
DROP TABLE IF EXISTS dq.profiles;
DROP TABLE IF EXISTS dq.profile_tables;
DROP TABLE IF EXISTS dq.profile_runs;
"""
RESET_RULES_SQL = """
DROP VIEW  IF EXISTS dq.latest_results;
DROP TABLE IF EXISTS dq.results;
DROP TABLE IF EXISTS dq.scan_runs;
DROP TABLE IF EXISTS dq.rules;
"""
EXPECTED = {
    "profile_runs",
    "profile_tables",
    "profiles",
    "latest_profiles",
    "rules",
    "scan_runs",
    "results",
    "latest_results",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the dq tables.")
    parser.add_argument(
        "--reset", action="store_true", help="drop the profiling objects first"
    )
    parser.add_argument(
        "--reset-rules", action="store_true", help="drop the rule objects first"
    )
    args = parser.parse_args()

    engine = get_admin_engine()
    with engine.begin() as conn:  # all-or-nothing, commits when the block ends
        pg = conn.connection.driver_connection  # psycopg connection, same transaction
        if args.reset:
            pg.execute(RESET_PROFILING_SQL)
            log.info("Dropped existing profiling objects")
        if args.reset_rules:
            pg.execute(RESET_RULES_SQL)
            log.info("Dropped existing rule objects")
        for sql_file in SQL_FILES:
            pg.execute(
                sql_file.read_text(encoding="utf-8")
            )  # no params: several statements OK
            log.info("Applied %s", sql_file.relative_to(PROJECT_ROOT))

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT t.table_name, t.table_type, count(c.column_name) "
                "FROM information_schema.tables t "
                "JOIN information_schema.columns c "
                "  ON c.table_schema = t.table_schema AND c.table_name = t.table_name "
                "WHERE t.table_schema = 'dq' "
                "GROUP BY t.table_name, t.table_type ORDER BY t.table_name"
            )
        ).all()
        reader_usage = conn.execute(
            text("SELECT has_schema_privilege('t2s_reader', 'dq', 'USAGE')")
        ).scalar_one()

    print("\nObjects in schema dq")
    print("-" * 52)
    for name, kind, n_cols in rows:
        print(f"  {name:<20}{kind:<14}{n_cols:>3} columns")
    print("-" * 52)
    print(f"  t2s_reader can use schema dq: {reader_usage}   (expected: False)")

    missing = EXPECTED - {r[0] for r in rows}
    if missing:
        print("MISSING:", ", ".join(sorted(missing)))
        return 1
    return 1 if reader_usage else 0


if __name__ == "__main__":
    sys.exit(main())
