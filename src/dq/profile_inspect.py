"""Run:  python -m src.dq.profile_inspect [--include-bird]
READ-ONLY inspection before building the profiler (Block 3, Step 1).
Prints: real row counts, column types, names needing quotes, a null preview for
sales.orders, a timing test on the largest table, and the current state of the dq schema.
One-off helper: it is not used by the profiler itself."""

import argparse
import re
import sys
import time
from collections import Counter, defaultdict

from sqlalchemy import text

from src.common.db import get_admin_engine
from src.ingestion.build_domains import load_domains

PLAIN_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")

NUMERIC = {
    "smallint",
    "integer",
    "bigint",
    "numeric",
    "real",
    "double precision",
    "decimal",
}
TEMPORAL = {
    "date",
    "timestamp without time zone",
    "timestamp with time zone",
    "time without time zone",
    "time with time zone",
}
TEXTUAL = {"text", "character varying", "character"}


def qi(name: str) -> str:
    """Quote an identifier safely."""
    return '"' + name.replace('"', '""') + '"'


def category(data_type: str) -> str:
    t = data_type.lower()
    if t in NUMERIC:
        return "numeric"
    if t in TEMPORAL:
        return "temporal"
    if t in TEXTUAL:
        return "text"
    if t == "boolean":
        return "boolean"
    return "other"


def header(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def fetch_columns(
    conn, schemas: list[str]
) -> dict[tuple[str, str], list[tuple[str, str]]]:
    """{(schema, table): [(column, data_type), ...]} for base tables only (no views)."""
    rows = conn.execute(
        text(
            "SELECT c.table_schema, c.table_name, c.column_name, c.data_type "
            "FROM information_schema.columns c "
            "JOIN information_schema.tables t "
            "  ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
            "WHERE t.table_type = 'BASE TABLE' AND c.table_schema = ANY(:s) "
            "ORDER BY c.table_schema, c.table_name, c.ordinal_position"
        ),
        {"s": list(schemas)},
    ).all()
    grouped: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for schema, table, column, dtype in rows:
        grouped[(schema, table)].append((column, dtype))
    return dict(grouped)


def section_olist(conn, tables) -> dict[tuple[str, str], int]:
    header("1. OLIST TABLES: real row counts and column types")
    print(
        f"{'table':<34}{'rows':>12}{'cols':>6}{'num':>6}{'text':>6}{'time':>6}{'other':>7}"
    )
    print("-" * 78)
    counts: dict[tuple[str, str], int] = {}
    for (schema, table), cols in tables.items():
        n = conn.execute(
            text(f"SELECT count(*) FROM {qi(schema)}.{qi(table)}")
        ).scalar_one()
        counts[(schema, table)] = n
        cats = Counter(category(t) for _, t in cols)
        other = cats["boolean"] + cats["other"]
        print(
            f"{schema + '.' + table:<34}{n:>12,}{len(cols):>6}"
            f"{cats['numeric']:>6}{cats['text']:>6}{cats['temporal']:>6}{other:>7}"
        )
    print("-" * 78)
    print(
        f"{'total':<34}{sum(counts.values()):>12,}{sum(len(c) for c in tables.values()):>6}"
    )
    return counts


def section_types(tables) -> None:
    header("2. DATA TYPES used in the Olist schemas")
    counter = Counter(t for cols in tables.values() for _, t in cols)
    for dtype, n in counter.most_common():
        print(f"  {dtype:<34}{n:>5} columns   ({category(dtype)})")


def odd_names(tables) -> list[str]:
    odd: list[str] = []
    for (schema, table), cols in tables.items():
        if not PLAIN_NAME.match(table):
            odd.append(f"{schema}.{table}")
        for col, _ in cols:
            if not PLAIN_NAME.match(col):
                odd.append(f"{schema}.{table}.{col}")
    return odd


def section_names(tables) -> None:
    header("3. NAMES THAT NEED QUOTING (Olist schemas)")
    odd = odd_names(tables)
    if not odd:
        print("  None: every table and column name is plain lowercase.")
    else:
        print(f"  {len(odd)} names need quoting, first 15:")
        for name in odd[:15]:
            print("   ", name)
    print(
        "  (The profiler will quote ALL identifiers anyway, because BIRD has odd names.)"
    )


def section_orders_preview(conn) -> None:
    header("4. PREVIEW: null counts in sales.orders (one query, one scan)")
    cols = [
        r[0]
        for r in conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'sales' AND table_name = 'orders' "
                "ORDER BY ordinal_position"
            )
        )
    ]
    if not cols:
        print("  sales.orders not found.")
        return
    parts = ", ".join(f"count({qi(c)})" for c in cols)
    sql = f"SELECT count(*), {parts} FROM sales.orders"
    print("SQL that ran:\n ", sql, "\n")
    row = conn.execute(text(sql)).one()
    total = row[0]
    print(f"  total rows: {total:,}")
    print(f"  {'column':<34}{'non-null':>10}{'nulls':>8}{'null %':>9}")
    for col, non_null in zip(cols, row[1:]):
        nulls = total - non_null
        pct = (nulls / total * 100) if total else 0.0
        print(f"  {col:<34}{non_null:>10,}{nulls:>8,}{pct:>8.2f}%")


def section_dq(conn) -> None:
    header("5. STATE OF THE dq SCHEMA")
    exists = conn.execute(
        text("SELECT 1 FROM pg_namespace WHERE nspname = 'dq'")
    ).scalar_one_or_none()
    if not exists:
        print("  Schema dq does not exist yet (expected: Step 2 creates it).")
        return
    names = [
        r[0]
        for r in conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'dq'"
            )
        )
    ]
    print("  Schema dq exists. Tables:", ", ".join(names) if names else "(none)")


def section_bird(conn) -> None:
    header("6. BIRD SCHEMAS (column summary only, no row counts)")
    schemas = [
        r[0]
        for r in conn.execute(
            text(
                "SELECT nspname FROM pg_namespace WHERE left(nspname, 5) = 'bird_' ORDER BY 1"
            )
        )
    ]
    tables = fetch_columns(conn, schemas)
    print(
        f"  {'schema':<30}{'tables':>7}{'cols':>6}{'num':>6}{'text':>6}"
        f"{'time':>6}{'other':>7}{'odd':>5}"
    )
    for schema in schemas:
        mine = {k: v for k, v in tables.items() if k[0] == schema}
        cats = Counter(category(t) for cols in mine.values() for _, t in cols)
        other = cats["boolean"] + cats["other"]
        n_cols = sum(len(c) for c in mine.values())
        print(
            f"  {schema:<30}{len(mine):>7}{n_cols:>6}{cats['numeric']:>6}"
            f"{cats['text']:>6}{cats['temporal']:>6}{other:>7}{len(odd_names(mine)):>5}"
        )
    print("  ('odd' = names that are not plain lowercase and so need quoting)")


def timed(conn, sql: str) -> float:
    started = time.perf_counter()
    conn.execute(text(sql)).all()
    return time.perf_counter() - started


def section_timing(conn, tables, counts) -> None:
    header("7. TIMING TEST on the largest Olist table")
    (schema, table), n = max(counts.items(), key=lambda kv: kv[1])
    cols = [c for c, _ in tables[(schema, table)]]
    target = f"{qi(schema)}.{qi(table)}"
    q_counts = (
        "SELECT count(*), "
        + ", ".join(f"count({qi(c)})" for c in cols)
        + f" FROM {target}"
    )
    q_distinct = (
        "SELECT "
        + ", ".join(f"count(DISTINCT {qi(c)})" for c in cols)
        + f" FROM {target}"
    )
    print(f"  table: {schema}.{table}  ({n:,} rows, {len(cols)} columns)")
    try:
        print(
            f"  non-null counts, all columns, ONE scan   : {timed(conn, q_counts):6.2f} s"
        )
        print(
            f"  distinct counts, all columns, ONE query  : {timed(conn, q_distinct):6.2f} s"
        )
    except Exception as exc:  # for example the 120 s timeout
        print("  Timing test failed:", str(exc).splitlines()[0])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only inspection before the profiler."
    )
    parser.add_argument(
        "--include-bird", action="store_true", help="also summarise bird_* schemas"
    )
    args = parser.parse_args()

    olist_schemas = list(load_domains().keys())
    with get_admin_engine().connect() as conn:
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")  # must be the first statement
        conn.exec_driver_sql("SET LOCAL statement_timeout = '120s'")

        tables = fetch_columns(conn, olist_schemas)
        if not tables:
            print("No tables found in", olist_schemas, "- is the Olist data loaded?")
            return 1
        counts = section_olist(conn, tables)
        section_types(tables)
        section_names(tables)
        section_orders_preview(conn)
        section_dq(conn)
        if args.include_bird:
            section_bird(conn)
        section_timing(
            conn, tables, counts
        )  # last: a timeout here cannot hide other output

    print("\nInspection finished (nothing was changed).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
