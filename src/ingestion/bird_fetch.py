"""Run:  python -m src.ingestion.bird_fetch
Optional flags:
  --url URL      override the download URL
  --force        re-download and re-extract even if files already exist
  --no-extract   only list the zip contents, do not extract

Block 2B, step 2. Downloads the BIRD Mini-Dev zip (databases + descriptions),
extracts it into data/bird/extracted, and prints what is inside:
  1) zip summary
  2) folder tree (file counts and sizes)
  3) every SQLite database: tables and row counts
  4) database_description CSV folders
  5) any .sql files (do they create DATABASES or SCHEMAS?)
  6) small JSON files (structure)
No Postgres access. Uses only the Python standard library.
Paste the full output back.

If the download fails: open the bird-bench/mini_dev GitHub README, download the
Mini-Dev zip in your browser, save it as data/bird/download/minidev.zip, then re-run.
"""

import argparse
import json
import sqlite3
import sys
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

from config.settings import PROJECT_ROOT

# VERIFY this URL in the bird-bench/mini_dev README (I cannot browse live).
DEFAULT_URL = "https://bird-bench.oss-cn-beijing.aliyuncs.com/minidev.zip"

BIRD_DIR = PROJECT_ROOT / "data" / "bird"
DOWNLOAD_DIR = BIRD_DIR / "download"
ZIP_PATH = DOWNLOAD_DIR / "minidev.zip"
EXTRACT_DIR = BIRD_DIR / "extracted"


def human(n) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(p)


def header(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


# ---------------------------------------------------------------- download
def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url}\n  -> {rel(dest)}")
    last = {"pct": -10}

    def hook(blocks, block_size, total):
        if total > 0:
            pct = int(blocks * block_size * 100 / total)
            if pct >= last["pct"] + 10:
                last["pct"] = pct
                done = min(blocks * block_size, total)
                print(f"  {min(pct, 100):>3}%  ({human(done)} of {human(total)})")

    urllib.request.urlretrieve(url, dest, reporthook=hook)
    print(f"Downloaded {human(dest.stat().st_size)}")


# ---------------------------------------------------------------- 1) zip
def summarize_zip(path: Path) -> None:
    header("1) Zip summary")
    with zipfile.ZipFile(path) as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        total = sum(i.file_size for i in infos)
        print(f"zip size         : {human(path.stat().st_size)}")
        print(f"files inside     : {len(infos)}")
        print(f"uncompressed size: {human(total)}")
        tops = Counter(i.filename.split("/")[0] for i in infos)
        print("top-level entries:")
        for name, count in sorted(tops.items()):
            print(f"  {count:>6} files  {name}")
        suffixes = Counter(Path(i.filename).suffix.lower() or "(none)" for i in infos)
        print("file types       :", dict(suffixes.most_common()))


def extract(path: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    print(f"\nExtracting to {rel(target)} ...")
    with zipfile.ZipFile(path) as zf:
        zf.extractall(target)
    print("Extraction done.")


# ---------------------------------------------------------------- 2) tree
def show_tree(root: Path) -> None:
    header("2) Folder tree (depth up to 3)")
    counts: Counter = Counter()
    sizes: Counter = Counter()
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        parts = f.relative_to(root).parts[:-1]
        for depth in range(1, min(len(parts), 3) + 1):
            key = "/".join(parts[:depth])
            counts[key] += 1
            sizes[key] += f.stat().st_size
    if not counts:
        print("(no sub-folders; files are directly in the root)")
    for key in sorted(counts):
        print(f"  {counts[key]:>6} files  {human(sizes[key]):>10}  {key}/")
    nested = list(root.rglob("*.zip"))
    if nested:
        print("\nNESTED ZIPS FOUND (need another extraction step):")
        for z in nested:
            print(f"  {human(z.stat().st_size):>10}  {rel(z)}")


# ---------------------------------------------------------------- 3) sqlite
def show_sqlite(root: Path) -> None:
    header("3) SQLite databases")
    files = sorted(list(root.rglob("*.sqlite")) + list(root.rglob("*.db")))
    if not files:
        print("No .sqlite / .db files found.")
        return
    grand_tables = grand_rows = 0
    for f in files:
        print(f"\n{f.stem}   ({human(f.stat().st_size)})   {rel(f)}")
        try:
            conn = sqlite3.connect(f.resolve().as_uri() + "?mode=ro", uri=True)
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            db_rows = 0
            for t in tables:
                safe = t.replace('"', '""')
                n = conn.execute(f'SELECT COUNT(*) FROM "{safe}"').fetchone()[0]
                db_rows += n
                print(f"    {n:>10,}  {t}")
            conn.close()
            print(f"    -> {len(tables)} tables, {db_rows:,} rows")
            grand_tables += len(tables)
            grand_rows += db_rows
        except Exception as exc:
            print("    could not read:", type(exc).__name__, str(exc)[:200])
    print(
        f"\nTOTAL: {len(files)} databases, {grand_tables} tables, {grand_rows:,} rows"
    )


# ---------------------------------------------------------------- 4) descriptions
def show_descriptions(root: Path) -> None:
    header("4) database_description folders (human-written column descriptions)")
    dirs = sorted(
        d for d in root.rglob("*") if d.is_dir() and d.name == "database_description"
    )
    if not dirs:
        print("No 'database_description' folders found.")
        return
    for d in dirs:
        csvs = sorted(d.glob("*.csv"))
        print(f"\n{rel(d)}: {len(csvs)} csv files")
        if csvs:
            first = csvs[0]
            try:
                with open(first, "r", encoding="utf-8-sig", errors="replace") as fh:
                    line = fh.readline().strip()
                print(f"    {first.name} header: {line[:160]}")
            except Exception as exc:
                print("    could not read header:", exc)


# ---------------------------------------------------------------- 5) sql files
SQL_MARKERS = (
    "create database",
    "\\connect",
    "\\c ",
    "create schema",
    "create table",
    "copy ",
    "insert into",
    "set search_path",
)


def show_sql_files(root: Path) -> None:
    header("5) .sql files (dumps and gold SQL)")
    files = sorted(root.rglob("*.sql"))
    if not files:
        print("No .sql files found.")
        return
    for f in files:
        print(f"\n{rel(f)}   ({human(f.stat().st_size)})")
        counts: Counter = Counter()
        head: list[str] = []
        total_lines = 0
        with open(f, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                total_lines += 1
                if len(head) < 10:
                    head.append(line.rstrip()[:150])
                low = line.lstrip().lower()
                for m in SQL_MARKERS:
                    if low.startswith(m):
                        counts[m.strip()] += 1
        print(f"  lines: {total_lines:,}")
        print(
            "  statement counts:",
            dict(counts) if counts else "(none of the tracked markers)",
        )
        print("  first lines:")
        for h in head:
            print("   |", h)


# ---------------------------------------------------------------- 6) json
def show_json(root: Path) -> None:
    header("6) JSON files (files under 20 MB)")
    files = sorted(
        f for f in root.rglob("*.json") if f.stat().st_size < 20 * 1024 * 1024
    )
    if not files:
        print("No small JSON files found.")
        return
    for f in files:
        print(f"\n{rel(f)}   ({human(f.stat().st_size)})")
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                print(f"  list of {len(data)} items")
                if data and isinstance(data[0], dict):
                    print("  first item keys:", list(data[0].keys())[:12])
            elif isinstance(data, dict):
                print(f"  dict with {len(data)} keys:", list(data.keys())[:12])
            else:
                print("  type:", type(data).__name__)
        except Exception as exc:
            print("  could not parse:", type(exc).__name__, str(exc)[:150])


# ---------------------------------------------------------------- main
def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Download and inspect BIRD Mini-Dev zip"
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument(
        "--force", action="store_true", help="re-download and re-extract"
    )
    parser.add_argument(
        "--no-extract", action="store_true", help="only list zip contents"
    )
    args = parser.parse_args()

    # --- download (or reuse) ---
    if args.force or not ZIP_PATH.exists():
        try:
            download(args.url, ZIP_PATH)
        except Exception as exc:
            print("\nDownload failed:", type(exc).__name__, str(exc)[:300])
            print("Fallback: download the Mini-Dev zip in your browser from the")
            print("bird-bench/mini_dev GitHub README, save it as:")
            print(f"  {rel(ZIP_PATH)}")
            print("then run this command again.")
            return 1
    else:
        print(
            f"Using existing zip {rel(ZIP_PATH)} ({human(ZIP_PATH.stat().st_size)}). "
            "Use --force to re-download."
        )

    if not zipfile.is_zipfile(ZIP_PATH):
        print("\nThe downloaded file is NOT a valid zip (often an HTML error page).")
        with open(ZIP_PATH, "rb") as fh:
            print("First bytes:", fh.read(200))
        print("Delete the file and download it manually (see fallback above).")
        return 1

    # --- summary + extract ---
    summarize_zip(ZIP_PATH)
    if args.no_extract:
        return 0

    already = EXTRACT_DIR.exists() and any(EXTRACT_DIR.iterdir())
    if args.force or not already:
        extract(ZIP_PATH, EXTRACT_DIR)
    else:
        print(
            f"\nUsing existing extraction in {rel(EXTRACT_DIR)} (use --force to redo)."
        )

    # --- inspect ---
    show_tree(EXTRACT_DIR)
    show_sqlite(EXTRACT_DIR)
    show_descriptions(EXTRACT_DIR)
    show_sql_files(EXTRACT_DIR)
    show_json(EXTRACT_DIR)
    print("\nDone. Paste the full output back.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
