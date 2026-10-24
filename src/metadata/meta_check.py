"""Run:  python -m src.metadata.meta_check [--source olist]
Read-only. Coverage (SQL vs Python), empties, role/status mix, PII list, samples."""

import argparse

from sqlalchemy import text

from src.common.db import get_admin_engine

COVERAGE_SQL = text("""
    SELECT count(*) FROM dq.latest_profiles p WHERE p.source_id = :s AND NOT EXISTS (
      SELECT 1 FROM meta.columns m WHERE m.source_id = p.source_id AND m.schema_name = p.schema_name
        AND m.table_name = p.table_name AND m.column_name = p.column_name)""")


def keys(conn, sql: str, s: str) -> set:
    return {tuple(r) for r in conn.execute(text(sql), {"s": s})}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="olist")
    s = ap.parse_args().source
    problems = []
    with get_admin_engine().connect() as c:
        prof = keys(
            c,
            "SELECT schema_name, table_name, column_name FROM dq.latest_profiles "
            "WHERE source_id = :s",
            s,
        )
        meta = keys(
            c,
            "SELECT schema_name, table_name, column_name FROM meta.columns "
            "WHERE source_id = :s",
            s,
        )
        missing_sql = c.execute(COVERAGE_SQL, {"s": s}).scalar()
        missing_py = len(prof - meta)
        no_table = c.execute(
            text(
                "SELECT count(*) FROM (SELECT DISTINCT schema_name, table_name FROM meta.columns "
                "WHERE source_id = :s) x WHERE NOT EXISTS (SELECT 1 FROM meta.tables t WHERE "
                "t.source_id = :s AND t.schema_name = x.schema_name AND t.table_name = x.table_name)"
            ),
            {"s": s},
        ).scalar()
        empty = c.execute(
            text(
                "SELECT count(*) FROM meta.columns WHERE source_id = :s AND "
                "length(trim(description)) = 0"
            ),
            {"s": s},
        ).scalar()
        status = c.execute(
            text(
                "SELECT status, count(*) FROM meta.columns WHERE source_id = :s "
                "GROUP BY 1 ORDER BY 1"
            ),
            {"s": s},
        ).all()
        roles = c.execute(
            text(
                "SELECT column_role, count(*) FROM meta.columns WHERE source_id = :s "
                "GROUP BY 1 ORDER BY 2 DESC"
            ),
            {"s": s},
        ).all()
        pii = c.execute(
            text(
                "SELECT table_name, column_name, pii_reason FROM meta.columns "
                "WHERE source_id = :s AND is_pii ORDER BY 1, 2"
            ),
            {"s": s},
        ).all()
        run = c.execute(
            text(
                "SELECT status, model, columns_done FROM meta.generation_runs "
                "WHERE source_id = :s ORDER BY started_at DESC LIMIT 1"
            ),
            {"s": s},
        ).first()
        samples = c.execute(
            text(
                "SELECT table_name, column_name, description, synonyms FROM meta.columns "
                "WHERE source_id = :s ORDER BY md5(column_name) LIMIT 5"
            ),
            {"s": s},
        ).all()

    print(
        f"profiled columns {len(prof)} | metadata columns {len(meta)} | latest run {tuple(run) if run else None}"
    )
    print(f"missing (SQL anti-join) {missing_sql} | missing (Python sets) {missing_py}")
    print(f"tables without meta.tables row {no_table} | empty descriptions {empty}")
    print("status:", dict(status), "| roles:", dict(roles))
    print(f"\nPII-flagged columns ({len(pii)}):")
    for t, col, why in pii:
        print(f"  {t}.{col}: {why}")
    print("\nSamples:")
    for t, col, d, syn in samples:
        print(f"  {t}.{col}: {d}  {list(syn)}")

    if missing_sql != missing_py:
        problems.append("SQL and Python coverage disagree")
    if missing_sql or no_table or empty:
        problems.append("gaps in coverage")
    print("\nRESULT:", "OK" if not problems else problems)
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
