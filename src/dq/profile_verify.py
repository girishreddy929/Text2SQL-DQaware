"""Run:  python -m src.dq.profile_verify [--source olist]
Independent check of the newest COMPLETED profile run. Recomputes counts, nulls, distinct,
min/max, mean and the #1 top value with DIFFERENT SQL than the profiler, then compares.
Read-only. Exit code 0 only if everything matches."""

import argparse
import math
import sys
from itertools import groupby

from sqlalchemy import text

from src.common.db import get_admin_engine
from src.dq.profiler_sql import load_profiler_config, qi


def close(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(float(a), float(b), rel_tol=1e-6, abs_tol=1e-4)


def verify_column(conn, p, cfg) -> tuple[int, list[str]]:
    """Returns (number of checks, list of mismatch descriptions)."""
    t = f"{qi(p['schema_name'])}.{qi(p['table_name'])}"
    c = qi(p["column_name"])
    name = f"{p['schema_name']}.{p['table_name']}.{p['column_name']}"
    checks, bad = 0, []

    def compare(what, stored, fresh, numeric=True):
        nonlocal checks
        checks += 1
        ok = close(stored, fresh) if numeric else stored == fresh
        if not ok:
            bad.append(f"{name}: {what} stored={stored!r} independent={fresh!r}")

    parts = [f"count(*) FILTER (WHERE {c} IS NULL)"]
    if p["distinct_count"] is not None:
        parts.append(
            f"(SELECT count(*) FROM (SELECT DISTINCT {c} FROM {t} WHERE {c} IS NOT NULL) d)"
        )
    row = conn.execute(text(f"SELECT {', '.join(parts)} FROM {t}")).one()
    compare("null_count", p["null_count"], row[0])
    if p["distinct_count"] is not None:
        compare("distinct_count", p["distinct_count"], row[1])

    if p["min_value"] is not None:
        for what, direction in (("min_value", "ASC"), ("max_value", "DESC")):
            fresh = conn.execute(
                text(
                    f"SELECT {c}::text AS _verify_value FROM {t} WHERE {c} IS NOT NULL ORDER BY {c} {direction} LIMIT 1"
                )
            ).scalar_one_or_none()
            compare(what, p[what], fresh, numeric=False)

    if p["mean_value"] is not None:
        fresh = conn.execute(
            text(
                f"SELECT sum({c}::numeric)::double precision / nullif(count({c}), 0) FROM {t}"
            )
        ).scalar_one()
        compare("mean_value", p["mean_value"], fresh)

    top = p["top_values"]
    if top and len(top[0]["value"]) < cfg.value_max_chars:
        fresh = conn.execute(
            text(f"SELECT count(*) FROM {t} WHERE {c}::text = :v"),
            {"v": top[0]["value"]},
        ).scalar_one()
        compare("top_value_1_count", top[0]["count"], fresh)
    return checks, bad


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Independently verify the newest profile run."
    )
    parser.add_argument("--source", default="olist")
    args = parser.parse_args()
    cfg = load_profiler_config()

    total_checks, problems = 0, []
    with get_admin_engine().connect() as conn:
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        conn.exec_driver_sql("SET LOCAL statement_timeout = '300s'")
        run = conn.execute(
            text(
                "SELECT run_id, started_at FROM dq.profile_runs WHERE source_id = :s "
                "AND status = 'completed' ORDER BY started_at DESC LIMIT 1"
            ),
            {"s": args.source},
        ).one_or_none()
        if run is None:
            print(
                f"No completed profile run for source {args.source!r}. Run the profiler first."
            )
            return 1
        print(f"Verifying run {run[0]} (started {run[1]:%Y-%m-%d %H:%M:%S})\n")
        profiles = (
            conn.execute(
                text(
                    "SELECT * FROM dq.profiles WHERE run_id = CAST(:r AS uuid) "
                    "ORDER BY schema_name, table_name, ordinal_position"
                ),
                {"r": str(run[0])},
            )
            .mappings()
            .all()
        )

        for (schema, table), group in groupby(
            profiles, key=lambda p: (p["schema_name"], p["table_name"])
        ):
            cols = list(group)
            t = f"{qi(schema)}.{qi(table)}"
            checks, bad = 0, []
            n = conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
            in_schema = conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.columns WHERE table_schema = :s AND table_name = :t"
                ),
                {"s": schema, "t": table},
            ).scalar_one()
            for what, stored, fresh in (
                ("row_count", cols[0]["row_count"], n),
                ("columns_profiled", len(cols), in_schema),
            ):
                checks += 1
                if stored != fresh:
                    bad.append(
                        f"{schema}.{table}: {what} stored={stored} independent={fresh}"
                    )
            for p in cols:
                c, b = verify_column(conn, p, cfg)
                checks += c
                bad += b
            total_checks += checks
            problems += bad
            print(
                f"{schema + '.' + table:<34}{len(cols):>4} cols{checks:>6} checks   {'OK' if not bad else 'MISMATCH'}"
            )

    print("-" * 62)
    if problems:
        print(f"{len(problems)} MISMATCHES out of {total_checks} checks:")
        for line in problems:
            print("  -", line)
        return 1
    print(f"ALL {total_checks} CHECKS MATCH")
    return 0


if __name__ == "__main__":
    sys.exit(main())
