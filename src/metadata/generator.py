"""Run:  python -m src.metadata.generator --source olist|bird:<db_id> [--tables schema.table ...] [--dry-run]
Reads dq.latest_profiles, asks Gemini, writes meta.tables / meta.columns as 'draft'."""

import argparse
import time
import uuid

from sqlalchemy import text

from src.common.db import get_admin_engine
from src.common.llm import get_chat_model, get_provider
from src.common.logging import get_logger
from src.metadata.llm_generate import build_chain, generate_table
from src.metadata.models import PROMPT_VERSION

log = get_logger(__name__)

PROFILES_SQL = text("""
    SELECT schema_name, table_name, column_name, ordinal_position, data_type, type_category,
           row_count, null_pct, distinct_count, min_value, max_value, top_values
    FROM dq.latest_profiles WHERE source_id = :s
    ORDER BY schema_name, table_name, ordinal_position""")
START_RUN = text(
    "INSERT INTO meta.generation_runs (run_id, source_id, model, prompt_version) "
    "VALUES (:r, :s, :m, :v)"
)
FINISH_RUN = text(
    "UPDATE meta.generation_runs SET status='completed', finished_at=now(), "
    "tables_done=:t, columns_done=:c WHERE run_id=:r"
)
FAIL_RUN = text(
    "UPDATE meta.generation_runs SET status='failed', finished_at=now(), notes=:n "
    "WHERE run_id=:r"
)
UPSERT_TABLE = text("""
    INSERT INTO meta.tables (source_id, schema_name, table_name, description, synonyms, generated_by, run_id)
    VALUES (:s, :sc, :t, :d, :syn, :m, :r)
    ON CONFLICT (source_id, schema_name, table_name) DO UPDATE SET description = EXCLUDED.description,
      synonyms = EXCLUDED.synonyms, status = 'draft', generated_by = EXCLUDED.generated_by,
      run_id = EXCLUDED.run_id, updated_at = now()
    WHERE meta.tables.status <> 'approved'""")
UPSERT_COLUMN = text("""
    INSERT INTO meta.columns (source_id, schema_name, table_name, column_name, data_type, ordinal_position,
      description, synonyms, column_role, is_pii, pii_reason, generated_by, run_id)
    VALUES (:s, :sc, :t, :c, :dt, :pos, :d, :syn, :role, :pii, :why, :m, :r)
    ON CONFLICT (source_id, schema_name, table_name, column_name) DO UPDATE SET
      data_type = EXCLUDED.data_type, ordinal_position = EXCLUDED.ordinal_position,
      description = EXCLUDED.description, synonyms = EXCLUDED.synonyms, column_role = EXCLUDED.column_role,
      is_pii = EXCLUDED.is_pii, pii_reason = EXCLUDED.pii_reason, status = 'draft',
      generated_by = EXCLUDED.generated_by, run_id = EXCLUDED.run_id, updated_at = now()
    WHERE meta.columns.status <> 'approved'""")


def source_note(source: str) -> str:
    if source == "olist":
        return (
            "Olist Brazilian e-commerce marketplace (2016-2018): orders, payments, customers, "
            "reviews, products, sellers and marketing leads"
        )
    return f"BIRD benchmark database '{source.split(':', 1)[-1]}'"


def fail_run(engine, run_id, notes: str) -> None:
    with engine.begin() as conn:
        conn.execute(FAIL_RUN, {"r": run_id, "n": notes[:1000]})


def write_all(conn, source, run_id, model, results, profiles) -> tuple[int, int]:
    skipped = 0
    for (schema, table), meta in results.items():
        p = {"s": source, "sc": schema, "t": table, "m": model, "r": run_id}
        skipped += (
            1
            - conn.execute(
                UPSERT_TABLE,
                {**p, "d": meta.table_description, "syn": meta.table_synonyms},
            ).rowcount
        )
        by_name = {x["column_name"]: x for x in profiles[(schema, table)]}
        for c in meta.columns:
            prof = by_name[c.column_name]
            skipped += (
                1
                - conn.execute(
                    UPSERT_COLUMN,
                    {
                        **p,
                        "c": c.column_name,
                        "dt": prof["data_type"],
                        "pos": prof["ordinal_position"],
                        "d": c.description,
                        "syn": c.synonyms,
                        "role": c.column_role,
                        "pii": c.is_pii,
                        "why": c.pii_reason,
                    },
                ).rowcount
            )
    return len(results), skipped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="olist")
    ap.add_argument("--tables", nargs="*", default=[])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engine = get_admin_engine()
    with engine.connect() as conn:
        rows = [
            dict(r) for r in conn.execute(PROFILES_SQL, {"s": args.source}).mappings()
        ]
    profiles: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        if not args.tables or f"{r['schema_name']}.{r['table_name']}" in args.tables:
            profiles.setdefault((r["schema_name"], r["table_name"]), []).append(r)
    if not profiles:
        print("No profiles found. Run: python -m src.dq.profiler --source", args.source)
        return 1

    model = get_provider().chat_model_name
    chain, run_id = build_chain(get_chat_model()), uuid.uuid4()
    if not args.dry_run:
        with engine.begin() as conn:
            conn.execute(
                START_RUN,
                {"r": run_id, "s": args.source, "m": model, "v": PROMPT_VERSION},
            )

    results, failures = {}, {}
    for (schema, table), cols in profiles.items():
        t0 = time.time()
        try:
            results[(schema, table)] = generate_table(
                chain,
                source_note(args.source),
                schema,
                table,
                cols[0]["row_count"],
                cols,
            )
            log.info(
                "%s.%s: %d columns in %.1fs", schema, table, len(cols), time.time() - t0
            )
        except Exception as exc:
            failures[f"{schema}.{table}"] = str(exc)
            log.error("%s.%s FAILED: %s", schema, table, exc)

    if failures:
        if not args.dry_run:
            fail_run(
                engine, run_id, "; ".join(f"{k}: {v}" for k, v in failures.items())
            )
        print("FAILED tables:", list(failures), "- nothing was written")
        return 1
    n_cols = sum(len(m.columns) for m in results.values())
    if args.dry_run:
        print(f"DRY RUN ok: {len(results)} tables, {n_cols} columns (nothing written)")
        return 0
    try:
        with engine.begin() as conn:
            tables, skipped = write_all(
                conn, args.source, run_id, model, results, profiles
            )
            conn.execute(FINISH_RUN, {"r": run_id, "t": tables, "c": n_cols})
    except Exception as exc:
        fail_run(engine, run_id, str(exc))
        raise
    print(
        f"run {run_id}: {tables} tables, {n_cols} columns written as draft "
        f"({skipped} approved rows left untouched)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
