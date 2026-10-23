"""Score the latest DQ results of one source and verify with an independent SQL query.

python -m src.dq.score_run [--source olist]
"""

from __future__ import annotations

import argparse

from sqlalchemy import text

from src.common.db import get_admin_engine
from src.dq.scoring import Score, Scorecard, band, build_scorecard, show

RESULTS_SQL = text("""
    SELECT rule_id, schema_name, table_name, dimension, pass_pct, passed, status, scanned_at
    FROM dq.latest_results WHERE source_id = :source""")

# Different formulation: Postgres computes the averages (rounded half away from zero).
INDEPENDENT_SQL = text("""
    WITH s AS (
        SELECT * FROM dq.latest_results
        WHERE source_id = :source AND status <> 'error' AND pass_pct IS NOT NULL)
    SELECT 'overall' AS grp, 'overall' AS label, round(avg(pass_pct), 2) AS score,
           count(*) FILTER (WHERE passed) AS n_passed, count(*) AS n FROM s
    UNION ALL
    SELECT 'dimension', dimension, round(avg(pass_pct), 2),
           count(*) FILTER (WHERE passed), count(*) FROM s GROUP BY dimension
    UNION ALL
    SELECT 'table', schema_name || '.' || table_name, round(avg(pass_pct), 2),
           count(*) FILTER (WHERE passed), count(*) FROM s GROUP BY schema_name, table_name""")


def load_results(source: str) -> list[dict]:
    with get_admin_engine().connect() as conn:
        return [
            dict(r) for r in conn.execute(RESULTS_SQL, {"source": source}).mappings()
        ]


def independent_scores(source: str) -> dict[tuple[str, str], tuple]:
    with get_admin_engine().connect() as conn:
        rows = conn.execute(INDEPENDENT_SQL, {"source": source}).mappings().all()
    return {(r["grp"], r["label"]): (r["score"], r["n_passed"], r["n"]) for r in rows}


def key(s: Score) -> tuple:
    return (s.score, s.passed, s.rules)


def card_scores(card: Scorecard) -> dict[tuple[str, str], tuple]:
    out = {("overall", "overall"): key(card.overall)}
    out.update({("dimension", s.name): key(s) for s in card.dimensions})
    out.update({("table", s.name): key(s) for s in card.tables})
    return out


def compare(python_side: dict, sql_side: dict) -> int:
    bad = 0
    for k in sorted(set(python_side) | set(sql_side)):
        if python_side.get(k) != sql_side.get(k):
            bad += 1
            print(f"  MISMATCH {k}: python={python_side.get(k)} sql={sql_side.get(k)}")
    return bad


def print_card(card: Scorecard, total: int, scanned_at) -> None:
    print(
        f"Latest scan: {scanned_at} | rules in results: {total} | errored: {len(card.errored)}"
    )
    print("\nOverall:")
    show(card.overall)
    print("\nBy dimension:")
    for s in card.dimensions:
        show(s)
    print("\nBy table (worst first):")
    for s in card.tables:
        show(s)
    print(f"\nFailing rules ({len(card.worst_rules)}), lowest pass % first:")
    for rule_id, pct in card.worst_rules:
        print(f"  {pct:>7.2f}  {rule_id}")
    if card.errored:
        print("\nErrored rules (not scored):", ", ".join(card.errored))


def main() -> int:
    ap = argparse.ArgumentParser(description="Score the latest DQ results")
    ap.add_argument("--source", default="olist")
    args = ap.parse_args()
    rows = load_results(args.source)
    if not rows:
        print(
            f"No results for {args.source}. Run: python -m src.dq.runner --source {args.source}"
        )
        return 1
    card = build_scorecard(rows)
    print_card(card, len(rows), max(r["scanned_at"] for r in rows))

    python_side, sql_side = card_scores(card), independent_scores(args.source)
    bad = compare(python_side, sql_side)
    print(
        f"\nIndependent SQL check: {len(python_side)} scores compared, {bad} mismatches"
    )
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
