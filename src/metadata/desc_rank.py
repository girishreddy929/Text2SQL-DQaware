"""Run:  python -m src.metadata.desc_rank [--source bird:california_schools]
Within each table: does our description retrieve ITS human description (top-1 / top-3 / MRR)?"""

import argparse
import statistics
from collections import defaultdict

from src.common.db import get_admin_engine
from src.metadata.desc_score import PAIRS_SQL, cosine, embed_all


def group_by_table(tables: list[str]) -> dict[str, list[int]]:
    groups = defaultdict(list)
    for i, t in enumerate(tables):
        groups[t].append(i)
    return groups


def rank_sorted(sims: list[tuple[float, int]], i: int) -> int:
    own = next(s for s, j in sims if j == i)
    scores = sorted((s for s, _ in sims), reverse=True)
    return scores.index(own) + 1


def rank_counted(sims: list[tuple[float, int]], i: int) -> int:
    own = next(s for s, j in sims if j == i)
    return 1 + sum(1 for s, j in sims if j != i and s > own)


def ranks(gen, ref, tables) -> list[int | None]:
    groups, out = group_by_table(tables), []
    for i, t in enumerate(tables):
        members = groups[t]
        if len(members) < 2:
            out.append(None)
            continue
        sims = [(cosine(gen[i], ref[j]), j) for j in members]
        a, b = rank_sorted(sims, i), rank_counted(sims, i)
        if a != b:
            raise AssertionError(f"rank formulations disagree for row {i}: {a} vs {b}")
        out.append(a)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="bird:california_schools")
    source = ap.parse_args().source
    with get_admin_engine().connect() as conn:
        rows = [tuple(r) for r in conn.execute(PAIRS_SQL, {"s": source})]
    if not rows:
        print("No pairs: run generator and ref_loader first.")
        return 1
    vecs = embed_all([r[3] for r in rows] + [r[4] for r in rows])
    gen, ref = vecs[: len(rows)], vecs[len(rows) :]
    tables = [r[1] for r in rows]
    rk = ranks(gen, ref, tables)
    groups = group_by_table(tables)
    used = [(i, r) for i, r in enumerate(rk) if r is not None]
    top1 = sum(1 for _, r in used if r == 1) / len(used)
    top3 = sum(1 for _, r in used if r <= 3) / len(used)
    mrr = statistics.mean(1 / r for _, r in used)
    random_top1 = statistics.mean(1 / len(groups[tables[i]]) for i, _ in used)
    print(
        f"{len(used)} columns | top-1 {top1:.1%} | top-3 {top3:.1%} | MRR {mrr:.3f} "
        f"| random top-1 would be {random_top1:.1%}"
    )
    print("\nMisses (rank > 3):")
    for i, r in used:
        if r > 3:
            best = max(groups[tables[i]], key=lambda j: cosine(gen[i], ref[j]))
            print(
                f"  rank {r:2} {tables[i]}.{rows[i][2]} | human says: {rows[i][4][:60]!r} "
                f"| closest human text belongs to {rows[best][2]}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
