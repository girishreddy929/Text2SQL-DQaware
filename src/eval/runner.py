# src/eval/runner.py
import yaml
import time
import argparse
from pathlib import Path
from sqlalchemy import text

from src.common.db import get_reader_engine
from src.common.logging import get_logger
from src.text2sql.baseline.chain import run_baseline
from src.eval.comparer import compare_results

logger = get_logger(__name__)


def load_golden_set(path="config/golden_olist.yaml"):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Golden set not found at {path}")
    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        return data.get("questions", data) if isinstance(data, dict) else data


def execute_gold(engine, sql: str) -> list[dict]:
    if not sql:
        return []
    try:
        with engine.connect() as conn:
            res = conn.execute(text(sql))
            return [dict(row) for row in res.mappings()]
    except Exception as e:
        logger.error(f"Gold SQL failed to execute: {e}")
        return []


def run_evaluation(limit: int = None, category: str = None):
    questions = load_golden_set()
    if category:
        questions = [q for q in questions if q.get("category") == category]
    if limit:
        questions = questions[:limit]

    engine = get_reader_engine()

    total = len(questions)
    correct = 0
    valid_sql = 0
    total_time = 0

    print(f"=== Evaluating {total} Golden Questions (Baseline) ===")

    for q in questions:
        q_id = q["id"]
        q_text = q["question"]
        gold_sql = q.get("gold_sql")
        cat = q.get("category", "unknown")

        start_t = time.time()
        # Pass default_limit=None to disable the LIMIT 100 guardrail in eval mode
        res = run_baseline(q_text, default_limit=None)
        elapsed = time.time() - start_t
        total_time += elapsed

        if res.is_valid:
            valid_sql += 1

        is_correct = False

        if gold_sql is None:
            # Malicious/Guardrail case: Passes if the baseline blocked it
            if not res.is_valid or res.error:
                is_correct = True
        else:
            gold_rows = execute_gold(engine, gold_sql)
            if res.is_valid and not res.error:
                order_sensitive = "ORDER BY" in gold_sql.upper()

                # FIX: Zip the columns and tuple rows into dictionaries
                pred_rows = []
                if res.query_result and res.query_result.rows:
                    cols = res.query_result.columns
                    pred_rows = [dict(zip(cols, row)) for row in res.query_result.rows]

                is_correct = compare_results(
                    gold_rows, pred_rows, order_sensitive=order_sensitive
                )

        if is_correct:
            print(f"[PASS] {q_id} ({cat}) - {int(elapsed * 1000)}ms")
            correct += 1
        else:
            print(f"[FAIL] {q_id} ({cat}) - {int(elapsed * 1000)}ms")
            print(f"       Gold: {gold_sql}")
            print(f"       Pred: {res.generated_sql}")
            if res.error:
                print(f"       Error: {res.error}")

    acc = (correct / total) * 100 if total else 0
    val = (valid_sql / total) * 100 if total else 0
    avg_t = total_time / total * 1000 if total else 0

    print("\n" + "=" * 45)
    print(f"Total Evaluated:       {total}")
    print(f"Valid SQL Rate:        {valid_sql}/{total} ({val:.1f}%)")
    print(f"Execution Accuracy:    {correct}/{total} ({acc:.1f}%)")
    print(f"Average Latency:       {avg_t:.1f}ms")
    print("=" * 45)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Baseline Pipeline")
    parser.add_argument("--limit", type=int, help="Max questions to run")
    parser.add_argument("--category", type=str, help="Filter by category")
    args = parser.parse_args()

    run_evaluation(limit=args.limit, category=args.category)
