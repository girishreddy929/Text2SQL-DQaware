"""Run:  python -m src.dq.profiler [--source olist|bird:<db_id>] [--tables schema.table ...]
                                   [--no-top-values]
Profiles every column of every table in the source and writes dq.profile_runs,
dq.profile_tables (with the exact stats SQL) and dq.profiles (with the top-values SQL).
Uses the ADMIN engine (agents never write). All profiling happens in ONE transaction."""

import argparse
import json
import sys
import time

from sqlalchemy import text

from src.common.db import get_admin_engine
from src.common.logging import get_logger
from src.dq.profiler_sql import (
    ColumnRef,
    ColumnStats,
    ProfilerConfig,
    build_stats_sql,
    build_top_values_sql,
    chunk_columns,
    format_top_values,
    load_profiler_config,
    parse_stats,
    qi,
    wants_top_values,
)
from src.ingestion.build_domains import load_domains

log = get_logger("profiler")

START_RUN = text(
    "INSERT INTO dq.profile_runs (source_id, schemas) "
    "VALUES (:source_id, CAST(:schemas AS text[])) RETURNING run_id"
)
FINISH_RUN = text(
    "UPDATE dq.profile_runs SET status = 'completed', finished_at = now(), "
    "tables_profiled = :t, columns_profiled = :c WHERE run_id = CAST(:run_id AS uuid)"
)
FAIL_RUN = text(
    "UPDATE dq.profile_runs SET status = 'failed', finished_at = now(), notes = :notes "
    "WHERE run_id = CAST(:run_id AS uuid)"
)
INSERT_TABLE = text(
    "INSERT INTO dq.profile_tables (run_id, source_id, schema_name, table_name, row_count, "
    "column_count, stats_sql, elapsed_ms) VALUES (CAST(:run_id AS uuid), :source_id, "
    ":schema_name, :table_name, :row_count, :column_count, :stats_sql, :elapsed_ms)"
)
INSERT_COLUMN = text(
    "INSERT INTO dq.profiles (run_id, source_id, schema_name, table_name, column_name, "
    "ordinal_position, data_type, type_category, row_count, null_count, null_pct, "
    "distinct_count, distinct_pct, min_value, max_value, mean_value, stddev_value, "
    "min_length, max_length, avg_length, top_values, top_values_sql) VALUES "
    "(CAST(:run_id AS uuid), :source_id, :schema_name, :table_name, :column_name, "
    ":ordinal_position, :data_type, :type_category, :row_count, :null_count, :null_pct, "
    ":distinct_count, :distinct_pct, :min_value, :max_value, :mean_value, :stddev_value, "
    ":min_length, :max_length, :avg_length, CAST(:top_values AS jsonb), :top_values_sql)"
)


def run_generated(conn, sql: str):
    """Run generated SQL that has NO bind parameters. text() escapes '%' for us; we escape
    ':' so odd column names (and ::casts) are never mistaken for bind parameters."""
    return conn.execute(text(sql.replace(":", "\\:")))


def resolve_source(source: str) -> list[str]:
    if source == "olist":
        return list(load_domains().keys())
    if source.startswith("bird:") and len(source) > 5:
        return [f"bird_{source.split(':', 1)[1]}"]
    raise SystemExit(f"Unknown --source {source!r}. Use 'olist' or 'bird:<db_id>'.")


def fetch_columns(conn, schemas: list[str]) -> dict[tuple[str, str], list[ColumnRef]]:
    rows = conn.execute(
        text(
            "SELECT c.table_schema, c.table_name, c.column_name, c.data_type, c.ordinal_position "
            "FROM information_schema.columns c JOIN information_schema.tables t "
            "  ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
            "WHERE t.table_type = 'BASE TABLE' AND c.table_schema = ANY(:s) "
            "ORDER BY c.table_schema, c.table_name, c.ordinal_position"
        ),
        {"s": list(schemas)},
    ).all()
    tables: dict[tuple[str, str], list[ColumnRef]] = {}
    for schema, table, column, dtype, position in rows:
        tables.setdefault((schema, table), []).append(
            ColumnRef(column, dtype, int(position))
        )
    return tables


def profile_table(
    conn,
    source_id: str,
    run_id: str,
    schema: str,
    table: str,
    columns: list[ColumnRef],
    cfg: ProfilerConfig,
    with_top_values: bool,
) -> tuple[list[ColumnStats], float]:
    started = time.perf_counter()
    stats: list[ColumnStats] = []
    sql_parts: list[str] = []
    for chunk in chunk_columns(columns, cfg.max_columns_per_query):
        sql = build_stats_sql(schema, table, chunk)
        sql_parts.append(sql)
        row = run_generated(conn, sql).mappings().one()
        stats.extend(parse_stats(chunk, row))

    for s in stats:
        if with_top_values and wants_top_values(s, cfg):
            top_sql = build_top_values_sql(schema, table, s.name, cfg)
            rows = run_generated(conn, top_sql).all()
            s.top_values = format_top_values([(r[0], r[1]) for r in rows], s.row_count)
            s.top_values_sql = top_sql

    elapsed_ms = (time.perf_counter() - started) * 1000
    row_count = stats[0].row_count if stats else 0
    conn.execute(
        INSERT_TABLE,
        {
            "run_id": run_id,
            "source_id": source_id,
            "schema_name": schema,
            "table_name": table,
            "row_count": row_count,
            "column_count": len(stats),
            "stats_sql": ";\n\n".join(sql_parts),
            "elapsed_ms": round(elapsed_ms, 1),
        },
    )
    conn.execute(
        INSERT_COLUMN,
        [
            {
                "run_id": run_id,
                "source_id": source_id,
                "schema_name": schema,
                "table_name": table,
                "column_name": s.name,
                "ordinal_position": s.position,
                "data_type": s.data_type,
                "type_category": s.category,
                "row_count": s.row_count,
                "null_count": s.null_count,
                "null_pct": s.null_pct,
                "distinct_count": s.distinct_count,
                "distinct_pct": s.distinct_pct,
                "min_value": s.min_value,
                "max_value": s.max_value,
                "mean_value": s.mean_value,
                "stddev_value": s.stddev_value,
                "min_length": s.min_length,
                "max_length": s.max_length,
                "avg_length": s.avg_length,
                "top_values": json.dumps(s.top_values)
                if s.top_values is not None
                else None,
                "top_values_sql": s.top_values_sql,
            }
            for s in stats
        ],
    )
    return stats, elapsed_ms / 1000


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Profile every column of a data source."
    )
    parser.add_argument(
        "--source", default="olist", help="olist (default) or bird:<db_id>"
    )
    parser.add_argument(
        "--tables", nargs="*", help="only these tables, e.g. sales.orders"
    )
    parser.add_argument(
        "--no-top-values", action="store_true", help="skip top-values queries"
    )
    args = parser.parse_args()

    cfg = load_profiler_config()
    source_id = args.source
    schemas = resolve_source(source_id)
    engine = get_admin_engine()

    with engine.connect() as conn:
        tables = fetch_columns(conn, schemas)
    if args.tables:
        wanted = set(args.tables)
        tables = {k: v for k, v in tables.items() if f"{k[0]}.{k[1]}" in wanted}
    if not tables:
        print(
            f"No tables found for source {source_id!r} (schemas {schemas}, filter {args.tables})."
        )
        return 1

    # Transaction 1: register the run and commit, so a failure can still be recorded.
    with engine.begin() as conn:
        run_id = str(
            conn.execute(
                START_RUN, {"source_id": source_id, "schemas": schemas}
            ).scalar_one()
        )
    log.info("Run %s started: source=%s, %d tables", run_id, source_id, len(tables))

    all_stats: list[tuple[str, ColumnStats]] = []
    try:
        # Transaction 2: all profiling + writes + 'completed', all or nothing.
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
            )  # first!
            conn.exec_driver_sql(
                f"SET LOCAL statement_timeout = '{cfg.statement_timeout_seconds}s'"
            )
            print(f"\n{'table':<40}{'rows':>12}{'cols':>6}{'seconds':>9}")
            print("-" * 67)
            for (schema, table), cols in tables.items():
                stats, seconds = profile_table(
                    conn,
                    source_id,
                    run_id,
                    schema,
                    table,
                    cols,
                    cfg,
                    not args.no_top_values,
                )
                all_stats.extend((f"{schema}.{table}", s) for s in stats)
                print(
                    f"{schema + '.' + table:<40}{stats[0].row_count:>12,}{len(stats):>6}{seconds:>9.2f}"
                )
            conn.execute(
                FINISH_RUN, {"run_id": run_id, "t": len(tables), "c": len(all_stats)}
            )
    except Exception as exc:
        # Transaction 3: the data was rolled back; record the failure.
        with engine.begin() as conn:
            conn.execute(FAIL_RUN, {"run_id": run_id, "notes": str(exc)[:500]})
        log.error("Run %s FAILED: %s", run_id, str(exc).splitlines()[0])
        raise

    print("-" * 67)
    print(f"Run {run_id} completed: {len(tables)} tables, {len(all_stats)} columns.")
    worst = sorted(
        (x for x in all_stats if x[1].null_pct > 0), key=lambda x: -x[1].null_pct
    )[:8]
    if worst:
        print("\nColumns with the most nulls in this run:")
        for table_name, s in worst:
            print(
                f"  {table_name + '.' + s.name:<52}{s.null_pct:>8.4f}%  ({s.null_count:,} rows)"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
