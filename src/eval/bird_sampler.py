"""Stratified sampler for BIRD Mini-Dev benchmark questions."""

from __future__ import annotations
from collections import defaultdict
import json
from pathlib import Path
import random

from config.settings import PROJECT_ROOT


def find_bird_json() -> Path:
    """Find the BIRD mini_dev_postgresql.json master file."""
    base_dir = PROJECT_ROOT / "data" / "bird"
    matches = list(base_dir.rglob("mini_dev_postgresql.json"))
    if not matches:
        raise FileNotFoundError(f"mini_dev_postgresql.json not found in {base_dir}")
    return matches[0]


def sample_stratified(
    questions: list[dict],
    target_count: int = 100,
    seed: int = 42,
) -> list[dict]:
    """Select a deterministic stratified sample preserving db_id and difficulty distribution."""
    rng = random.Random(seed)
    strata: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for q in questions:
        key = (q["db_id"], q.get("difficulty", "moderate"))
        strata[key].append(q)

    sorted_strata_keys = sorted(strata.keys())
    for key in sorted_strata_keys:
        rng.shuffle(strata[key])

    ratio = target_count / len(questions)
    sample: list[dict] = []
    remainders: list[tuple[float, tuple[str, str]]] = []

    for key in sorted_strata_keys:
        items = strata[key]
        exact_share = len(items) * ratio
        take = int(exact_share)
        sample.extend(items[:take])
        strata[key] = items[take:]
        remainders.append((exact_share - take, key))

    remainders.sort(key=lambda x: x[0], reverse=True)
    rem_idx = 0
    while len(sample) < target_count and rem_idx < len(remainders):
        key = remainders[rem_idx][1]
        if strata[key]:
            sample.append(strata[key].pop(0))
        rem_idx += 1

    sample.sort(key=lambda x: x["question_id"])
    return sample


def get_bird_sample(
    target_count: int = 100,
    seed: int = 42,
    out_path: Path | None = None,
) -> list[dict]:
    path = find_bird_json()
    with open(path, "r", encoding="utf-8") as f:
        questions = json.load(f)

    sampled = sample_stratified(questions, target_count=target_count, seed=seed)
    dest = out_path or (PROJECT_ROOT / "data" / "bird" / "mini_dev_sample_100.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(sampled, f, indent=2)
    return sampled


if __name__ == "__main__":
    sample = get_bird_sample(target_count=100)
    print(
        f"Sampled {len(sample)} questions across {len(set(q['db_id'] for q in sample))} databases."
    )
    diffs = defaultdict(int)
    for q in sample:
        diffs[q.get("difficulty", "unknown")] += 1
    print(
        f"Distribution: simple={diffs['simple']}, moderate={diffs['moderate']}, challenging={diffs['challenging']}"
    )
