"""src/metadata/kg_infer.py: Infer joins via naming heuristics and value overlap."""

from __future__ import annotations

import argparse
from sqlalchemy import text
from src.adapters.db.base import ColumnInfo
from src.common.db import get_admin_engine
from src.dq.profiler_sql import qi
from src.metadata.kg_models import JoinCandidate


def is_candidate_pair(c1: ColumnInfo, c2: ColumnInfo) -> bool:
    """True if columns from different tables look joinable by name and type."""
    if (c1.schema, c1.table) == (c2.schema, c2.table):
        return False
    if c1.data_type != c2.data_type:
        return False
    n1, n2 = c1.column.lower(), c2.column.lower()
    if n1 == n2 and ("id" in n1 or "code" in n1 or "name" in n1 or "prefix" in n1):
        return True
    if n1.endswith("zip_code_prefix") and n2.endswith("zip_code_prefix"):
        return True
    return False


def build_overlap_sql(c1: ColumnInfo, c2: ColumnInfo) -> str:
    """Compute distinct value intersection without full table joins."""
    t1 = f"{qi(c1.schema)}.{qi(c1.table)}"
    t2 = f"{qi(c2.schema)}.{qi(c2.table)}"
    return f"""
    WITH a AS (SELECT DISTINCT {qi(c1.column)} AS val FROM {t1} WHERE {qi(c1.column)} IS NOT NULL),
         b AS (SELECT DISTINCT {qi(c2.column)} AS val FROM {t2} WHERE {qi(c2.column)} IS NOT NULL),
         m AS (SELECT COUNT(*) AS matched FROM a JOIN b USING (val))
    SELECT (SELECT COUNT(*) FROM a) AS cnt_a,
           (SELECT COUNT(*) FROM b) AS cnt_b,
           (SELECT matched FROM m) AS cnt_m
    """


def measure_overlap(
    conn, c1: ColumnInfo, c2: ColumnInfo, min_overlap: float = 0.75
) -> JoinCandidate | None:
    """Execute overlap query and return JoinCandidate if threshold met."""
    row = conn.execute(text(build_overlap_sql(c1, c2))).mappings().one()
    cnt_a, cnt_b, cnt_m = row["cnt_a"], row["cnt_b"], row["cnt_m"]
    denom = min(cnt_a, cnt_b)
    if denom == 0:
        return None
    overlap = float(cnt_m) / denom
    if overlap >= min_overlap:
        return JoinCandidate(
            src_table=f"{c1.schema}.{c1.table}",
            tgt_table=f"{c2.schema}.{c2.table}",
            src_col=c1.column,
            tgt_col=c2.column,
            overlap_pct=round(overlap * 100, 2),
            reason=f"{c1.column} matches {c2.column} ({cnt_m}/{denom} = {overlap:.1%})",
        )
    return None


def infer_joins(
    conn, columns: list[ColumnInfo], min_overlap: float = 0.75
) -> list[JoinCandidate]:
    """Inspect all candidate pairs in column list and return valid joins."""
    joins: list[JoinCandidate] = []
    seen = set()
    for i, c1 in enumerate(columns):
        for c2 in columns[i + 1 :]:
            pair_key = tuple(
                sorted(
                    [
                        f"{c1.schema}.{c1.table}.{c1.column}",
                        f"{c2.schema}.{c2.table}.{c2.column}",
                    ]
                )
            )
            if pair_key in seen:
                continue
            if is_candidate_pair(c1, c2):
                seen.add(pair_key)
                candidate = measure_overlap(conn, c1, c2, min_overlap=min_overlap)
                if candidate:
                    joins.append(candidate)
    return joins


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="olist", choices=["olist"])
    parser.add_argument("--min-overlap", type=float, default=0.75)
    args = parser.parse_args()

    engine = get_admin_engine()
    schemas = (
        ["sales", "customer", "catalog", "marketing"] if args.source == "olist" else []
    )

    with engine.connect() as conn:
        q = text("""
            SELECT table_schema, table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = ANY(:schemas)
            ORDER BY table_schema, table_name, ordinal_position
        """)
        cols = [
            ColumnInfo(
                r["table_schema"],
                r["table_name"],
                r["column_name"],
                r["data_type"],
                r["is_nullable"] == "YES",
            )
            for r in conn.execute(q, {"schemas": schemas}).mappings()
        ]
        results = infer_joins(conn, cols, min_overlap=args.min_overlap)
        print(f"Found {len(results)} valid inferred joins for {args.source}:")
        for j in sorted(results, key=lambda x: (x.src_table, x.tgt_table)):
            print(
                f"  {j.src_table}.{j.src_col} <-> {j.tgt_table}.{j.tgt_col} ({j.overlap_pct}%)"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
