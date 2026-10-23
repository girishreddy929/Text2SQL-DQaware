"""Run:  python -m src.ingestion.bird_gold_check [--timeout 120] [--limit N]

Block 2B, step 5. Runs every BIRD gold query (PostgreSQL version) as the
read-only role t2s_reader, with search_path = bird_<db_id>. No LIMIT is added.
Writes:
  data/bird/gold_run.json       per-question status, rows, seconds, error
  data/bird/gold_failures.csv   failed questions with the error and the SQL
"""

import argparse
import csv
import json
import sys
import time
from collections import Counter, defaultdict

from config.settings import PROJECT_ROOT
from src.ingestion.bird_loader import get_admin_engine, qi

BIRD_DIR = PROJECT_ROOT / "data" / "bird"
QUESTIONS = BIRD_DIR / "extracted" / "minidev" / "MINIDEV" / "mini_dev_postgresql.json"
OUT_RUN = BIRD_DIR / "gold_run.json"
OUT_FAIL = BIRD_DIR / "gold_failures.csv"
READER = "t2s_reader"


def write_tests(conn) -> bool:
    """Try forbidden statements as the reader. Always rolled back."""
    tests = [
        (
            "INSERT",
            "INSERT INTO bird_superhero.alignment SELECT * FROM bird_superhero.alignment LIMIT 1",
        ),
        ("DELETE", "DELETE FROM bird_superhero.alignment"),
        ("CREATE TABLE", "CREATE TABLE bird_superhero.zz_test (x int)"),
        ("DROP TABLE", "DROP TABLE bird_superhero.alignment"),
    ]
    conn.autocommit = False
    all_blocked = True
    for name, sql in tests:
        try:
            with conn.cursor() as c:
                c.execute(sql)
            blocked = False
        except Exception:
            blocked = True
        conn.rollback()
        all_blocked &= blocked
        print(f"  {name:<14} -> {'BLOCKED (good)' if blocked else 'ALLOWED (BAD!)'}")
    conn.autocommit = True
    return all_blocked


def run_one(cur, sql: str) -> dict:
    t = time.time()
    try:
        cur.execute(sql)
        rows = cur.fetchall()
        n_cols = (
            len(rows[0]) if rows else (len(cur.description) if cur.description else 0)
        )
        return {
            "status": "ok" if rows else "empty",
            "n_rows": len(rows),
            "n_cols": n_cols,
            "seconds": round(time.time() - t, 3),
            "preview": [[str(v)[:40] for v in r] for r in rows[:3]],
            "error": None,
        }
    except Exception as exc:
        first = str(exc).splitlines()[0][:300] if str(exc) else type(exc).__name__
        return {
            "status": "error",
            "n_rows": 0,
            "n_cols": 0,
            "seconds": round(time.time() - t, 3),
            "preview": [],
            "error": f"{getattr(exc, 'sqlstate', None)}: {first}",
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run BIRD gold SQL as the read-only role"
    )
    parser.add_argument("--timeout", type=int, default=120, help="seconds per query")
    parser.add_argument(
        "--limit", type=int, default=0, help="only the first N questions"
    )
    args = parser.parse_args()

    if not QUESTIONS.exists():
        print("Missing file:", QUESTIONS)
        return 1
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    if args.limit:
        questions = questions[: args.limit]

    engine = get_admin_engine()
    raw = engine.raw_connection()
    conn = raw.driver_connection
    results: list[dict] = []
    t_start = time.time()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(f"SET ROLE {READER}")

        print(f"Write-protection test (as {READER}):")
        if not write_tests(conn):
            print(
                "\nGUARDRAIL FAILURE: the reader can write. Fix grants before going on."
            )
            return 1

        cur.execute(f"SET statement_timeout = {int(args.timeout * 1000)}")
        print(
            f"\nRunning {len(questions)} gold queries as {READER} (timeout {args.timeout}s)..."
        )

        for i, q in enumerate(questions, 1):
            cur.execute(f"SET search_path TO {qi('bird_' + q['db_id'])}")
            r = run_one(cur, q["SQL"])
            r["run_as"] = READER
            if r["status"] == "error":
                # Retry as admin to classify the failure.
                cur.execute("RESET ROLE")
                r2 = run_one(cur, q["SQL"])
                cur.execute(f"SET ROLE {READER}")
                r["admin_retry"] = r2["status"]
                r["failure_class"] = (
                    "permission/role problem (works as admin)"
                    if r2["status"] != "error"
                    else "SQL/data problem (fails for admin too)"
                )
            r.update(
                question_id=q["question_id"],
                db_id=q["db_id"],
                difficulty=q["difficulty"],
                sql=q["SQL"],
            )
            results.append(r)
            if i % 50 == 0:
                print(f"  {i}/{len(questions)} done")
    finally:
        try:
            conn.autocommit = True
            with conn.cursor() as c:
                c.execute("DISCARD ALL")  # clear SET ROLE / search_path before pooling
        except Exception:
            pass
        raw.close()

    # ------------------------------------------------ report
    OUT_RUN.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    failed = [r for r in results if r["status"] == "error"]
    with open(OUT_FAIL, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            ["question_id", "db_id", "difficulty", "failure_class", "error", "sql"]
        )
        for r in failed:
            w.writerow(
                [
                    r["question_id"],
                    r["db_id"],
                    r["difficulty"],
                    r["failure_class"],
                    r["error"],
                    r["sql"],
                ]
            )

    counts = Counter(r["status"] for r in results)
    print("\n" + "=" * 70)
    print("RESULT")
    print("=" * 70)
    print(
        f"total {len(results)}   ok {counts['ok']}   empty {counts['empty']}   error {counts['error']}"
    )
    print(f"time {time.time() - t_start:.0f}s")

    by_db: dict = defaultdict(Counter)
    by_diff: dict = defaultdict(Counter)
    for r in results:
        by_db[r["db_id"]][r["status"]] += 1
        by_diff[r["difficulty"]][r["status"]] += 1
    print(f"\n{'db_id':<26}{'ok':>5}{'empty':>7}{'error':>7}")
    for db in sorted(by_db):
        c = by_db[db]
        print(f"{db:<26}{c['ok']:>5}{c['empty']:>7}{c['error']:>7}")
    print(f"\n{'difficulty':<26}{'ok':>5}{'empty':>7}{'error':>7}")
    for d in ("simple", "moderate", "challenging"):
        c = by_diff[d]
        print(f"{d:<26}{c['ok']:>5}{c['empty']:>7}{c['error']:>7}")

    if failed:
        print("\nFailure classes:", dict(Counter(r["failure_class"] for r in failed)))
        print("Top error messages:")
        for msg, n in Counter(r["error"][:90] for r in failed).most_common(8):
            print(f"  {n:>3}x  {msg}")
        print("Failed question_ids:", [r["question_id"] for r in failed][:40])
    empties = [r["question_id"] for r in results if r["status"] == "empty"]
    if empties:
        print(
            f"\nQueries returning 0 rows ({len(empties)}), first 20 ids:", empties[:20]
        )
    slow = sorted(results, key=lambda r: r["seconds"], reverse=True)[:5]
    print("\nSlowest 5:", [(r["question_id"], r["seconds"]) for r in slow])
    print(f"\nsaved -> {OUT_RUN.relative_to(PROJECT_ROOT)}")
    print(f"saved -> {OUT_FAIL.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
