"""Run:  python -m src.metadata.init_schema [--reset]
Applies sql/04_meta_schema.sql (idempotent) and checks that t2s_reader cannot see meta."""

import argparse

from sqlalchemy import text

from config.settings import PROJECT_ROOT
from src.common.db import get_admin_engine
from src.common.logging import get_logger

log = get_logger(__name__)
SQL_FILE = PROJECT_ROOT / "sql" / "04_meta_schema.sql"
EXPECTED = {  # table -> number of columns
    "columns": 17,
    "description_scores": 10,
    "generation_runs": 10,
    "reference_descriptions": 9,
    "tables": 11,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--reset", action="store_true", help="DROP SCHEMA meta CASCADE first"
    )
    args = ap.parse_args()

    engine = get_admin_engine()
    with engine.begin() as conn:
        if args.reset:
            conn.execute(text("DROP SCHEMA IF EXISTS meta CASCADE"))
            log.info("meta schema dropped")
        conn.connection.driver_connection.execute(SQL_FILE.read_text("utf-8"))

    with engine.connect() as conn:
        found = dict(
            conn.execute(
                text(
                    "SELECT table_name, count(*) FROM information_schema.columns "
                    "WHERE table_schema = 'meta' GROUP BY 1 ORDER BY 1"
                )
            ).all()
        )
        reader_usage = conn.execute(
            text("SELECT has_schema_privilege('t2s_reader', 'meta', 'USAGE')")
        ).scalar()

    for name, n in found.items():
        print(f"  meta.{name:24} {n} columns")
    ok = found == EXPECTED and reader_usage is False
    print("t2s_reader USAGE on meta:", reader_usage)
    print("RESULT:", "OK" if ok else f"MISMATCH (expected {EXPECTED})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
