"""Run:  python -m src.ingestion.bird_inspect
Block 2B, step 1. Inspects the Hugging Face dataset birdsql/bird_mini_dev:
  1) lists the files in the repo with sizes (do the DATABASES live there, or only questions?)
  2) loads the questions and prints structure, difficulty and db_id counts, a sample
  3) saves every split to data/bird/<split>.json
No database access. Paste the full output back."""

import json
import sys
from collections import Counter

from config.settings import PROJECT_ROOT

REPO = "birdsql/bird_mini_dev"
BIRD_DIR = PROJECT_ROOT / "data" / "bird"


def human(n) -> str:
    if n is None:
        return "?"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def show_repo_files() -> None:
    from huggingface_hub import HfApi

    print("=" * 70)
    print(f"1) Files in Hugging Face repo {REPO}")
    print("=" * 70)
    info = HfApi().dataset_info(REPO, files_metadata=True)
    card = info.card_data
    print("license:", getattr(card, "license", None) if card else None)
    print("tags   :", info.tags)
    files = sorted(info.siblings or [], key=lambda f: f.rfilename)
    total = sum((f.size or 0) for f in files)
    for f in files:
        print(f"  {human(f.size):>10}  {f.rfilename}")
    print(f"  {len(files)} files, {human(total)} total")


def show_questions() -> None:
    from datasets import get_dataset_config_names, load_dataset

    print("\n" + "=" * 70)
    print("2) Questions via load_dataset")
    print("=" * 70)
    try:
        print("configs:", get_dataset_config_names(REPO))
    except Exception as exc:
        print("could not list configs:", type(exc).__name__, str(exc)[:200])

    ds = load_dataset(REPO)
    BIRD_DIR.mkdir(parents=True, exist_ok=True)
    for split, data in ds.items():
        print(f"\n--- split '{split}': {data.num_rows} rows ---")
        print("columns:", data.column_names)
        for col in ("difficulty", "db_id"):
            if col in data.column_names:
                print(f"{col}:", dict(Counter(data[col])))
        sample = {
            k: (str(v)[:160] + "...") if len(str(v)) > 160 else v
            for k, v in data[0].items()
        }
        print(
            "sample row:", json.dumps(sample, indent=2, ensure_ascii=False, default=str)
        )
        out = BIRD_DIR / f"{split}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(list(data), f, ensure_ascii=False, indent=2, default=str)
        print(f"saved -> {out.relative_to(PROJECT_ROOT)}")


def main() -> int:
    try:
        show_repo_files()
    except Exception as exc:
        print("repo file listing failed:", type(exc).__name__, str(exc)[:300])
    try:
        show_questions()
    except Exception as exc:
        print("\nload_dataset failed:", type(exc).__name__, str(exc)[:500])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
