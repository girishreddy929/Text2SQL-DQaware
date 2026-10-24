"""src/metadata/bird_fk.py: Extract ground-truth foreign keys from BIRD dev_tables.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.metadata.kg_models import JoinCandidate

BIRD_DATA_DIR = Path("data/bird")


def find_dev_tables_file() -> Path:
    for p in BIRD_DATA_DIR.rglob("dev_tables.json"):
        if p.is_file():
            return p
    raise FileNotFoundError("Could not find dev_tables.json under data/bird/")


def load_bird_fks(db_id: str) -> list[JoinCandidate]:
    """Load ground-truth foreign keys for db_id from dev_tables.json."""
    path = find_dev_tables_file()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    db_entry = next((item for item in data if item.get("db_id") == db_id), None)
    if not db_entry:
        return []

    tbl_names = db_entry["table_names_original"]
    col_names = db_entry["column_names_original"]
    fks = db_entry.get("foreign_keys", [])

    schema = f"bird_{db_id}"
    candidates: list[JoinCandidate] = []
    for src_idx, tgt_idx in fks:
        t_src_idx, c_src = col_names[src_idx]
        t_tgt_idx, c_tgt = col_names[tgt_idx]
        candidates.append(
            JoinCandidate(
                src_table=f"{schema}.{tbl_names[t_src_idx]}",
                tgt_table=f"{schema}.{tbl_names[t_tgt_idx]}",
                src_col=c_src,
                tgt_col=c_tgt,
                overlap_pct=100.0,
                reason="Ground-truth FK from dev_tables.json",
            )
        )
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-id", default="california_schools")
    args = parser.parse_args()

    fks = load_bird_fks(args.db_id)
    print(f"Found {len(fks)} ground-truth foreign keys for BIRD '{args.db_id}':")
    for fk in fks:
        print(f"  {fk.src_table}.{fk.src_col} -> {fk.tgt_table}.{fk.tgt_col}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
