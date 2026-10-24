"""Run:  python -m src.metadata.desc_score [--source bird:california_schools]
Embedding similarity between our drafts and BIRD's human descriptions -> meta.description_scores."""

import argparse
import math
import statistics
import uuid
from collections import defaultdict

from sqlalchemy import text

from src.common.db import get_admin_engine
from src.common.llm import get_embeddings, get_provider
from src.common.llm_guard import call_resilient

BATCH = 50
STRONG, FAIR = 0.80, 0.65  # heuristic bands for gemini-embedding-001
PAIRS_SQL = text("""
    SELECT m.schema_name, m.table_name, m.column_name, m.description, r.description
    FROM meta.columns m JOIN meta.reference_descriptions r
      ON r.source_id = m.source_id AND r.schema_name = m.schema_name
     AND r.table_name = m.table_name AND r.column_name = m.column_name
    WHERE m.source_id = :s AND r.description IS NOT NULL
    ORDER BY m.table_name, m.ordinal_position""")
INSERT = text("""
    INSERT INTO meta.description_scores (score_run_id, source_id, schema_name, table_name, column_name,
      generated_text, reference_text, similarity, embedding_model)
    VALUES (:r, :s, :sc, :t, :c, :g, :ref, :sim, :m)""")


def cosine(a, b) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


def partner_indices(tables: list[str]) -> list[int]:
    """For the control: pair each row with the next row of the SAME table (-1 if alone)."""
    groups = defaultdict(list)
    for i, t in enumerate(tables):
        groups[t].append(i)
    out = [-1] * len(tables)
    for idx in groups.values():
        if len(idx) > 1:
            for k, i in enumerate(idx):
                out[i] = idx[(k + 1) % len(idx)]
    return out


def band(sim: float) -> str:
    return "strong" if sim >= STRONG else "fair" if sim >= FAIR else "weak"


def embed_all(texts: list[str]) -> list[list[float]]:
    emb, out = get_embeddings(), []
    for i in range(0, len(texts), BATCH):
        out += call_resilient(emb.embed_documents, texts[i : i + BATCH])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="bird:california_schools")
    source = ap.parse_args().source
    engine = get_admin_engine()
    with engine.connect() as conn:
        rows = [tuple(r) for r in conn.execute(PAIRS_SQL, {"s": source})]
    if not rows:
        print("No pairs: run generator and ref_loader first.")
        return 1

    vecs = embed_all([r[3] for r in rows] + [r[4] for r in rows])
    gen, ref = vecs[: len(rows)], vecs[len(rows) :]
    sims = [cosine(g, r) for g, r in zip(gen, ref)]
    partner = partner_indices([r[1] for r in rows])
    control = [cosine(gen[i], ref[p]) for i, p in enumerate(partner) if p >= 0]

    model, run_id = get_provider().embedding_model_name, uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            INSERT,
            [
                {
                    "r": run_id,
                    "s": source,
                    "sc": sc,
                    "t": t,
                    "c": c,
                    "g": g,
                    "ref": rf,
                    "sim": round(s, 4),
                    "m": model,
                }
                for (sc, t, c, g, rf), s in zip(rows, sims)
            ],
        )

    print(f"score run {run_id} | {len(rows)} pairs | model {model}")
    print(
        f"mean {statistics.mean(sims):.4f} | median {statistics.median(sims):.4f} | "
        f"control (wrong column) mean {statistics.mean(control):.4f}"
    )
    for b in ("strong", "fair", "weak"):
        n = sum(1 for s in sims if band(s) == b)
        print(f"  {b:7} {n:4}  ({100 * n / len(sims):.1f}%)")
    by_table = defaultdict(list)
    for r, s in zip(rows, sims):
        by_table[r[1]].append(s)
    for t, v in by_table.items():
        print(f"  table {t:10} n={len(v):3} mean={statistics.mean(v):.4f}")
    print("\nWorst 5:")
    for (sc, t, c, g, rf), s in sorted(zip(rows, sims), key=lambda x: x[1])[:5]:
        print(f"  {s:.3f} {t}.{c}\n     ours : {g[:110]}\n     human: {rf[:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
