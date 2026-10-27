# src/eval/eval_agentic.py
import yaml
import time
import argparse
from pathlib import Path
from sqlalchemy import text

from src.common.db import get_reader_engine
from src.common.logging import get_logger
from src.text2sql.agents.graph import run_agentic_text2sql
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
    total_retries = 0

    # Setup file logging
    report_dir = Path("reports")
    report_dir.mkdir(exist_ok=True)
    report_file = report_dir / "agentic_eval_results.txt"

    with open(report_file, "w", encoding="utf-8") as f:

        def log_both(msg: str):
            print(msg)
            f.write(msg + "\n")

        log_both(f"Starting Agentic Evaluation on {total} questions...\n")

        for i, q in enumerate(questions, 1):
            q_text = q["question"]
            gold_sql = q.get("gold_sql")
            cat = q.get("category", "unknown")

            log_both(f"[{i}/{total}] [{cat}] {q_text}")

            start_t = time.time()
            state = run_agentic_text2sql(
                q_text, source_id="olist", chat_history=[], eval_mode=True
            )
            elapsed = time.time() - start_t
            total_time += elapsed

            pred_sql = state.get("generated_sql")
            pred_rows = state.get("execution_result", [])
            retries = state.get("retry_count", 0)
            total_retries += retries

            if state.get("is_valid_sql"):
                valid_sql += 1

            is_correct = False
            gold_rows = []

            if gold_sql is None:
                if (
                    not state.get("is_valid_sql")
                    or state.get("error_message")
                    or state.get("intent") == "out_of_scope"
                ):
                    is_correct = True
            else:
                gold_rows = execute_gold(engine, gold_sql)
                if state.get("is_valid_sql") and not state.get("error_message"):
                    order_sensitive = "ORDER BY" in gold_sql.upper()
                    is_correct = compare_results(
                        gold_rows, pred_rows, order_sensitive=order_sensitive
                    )

            if is_correct:
                log_both(f"  ✅ PASS in {elapsed:.1f}s (Retries: {retries})")
                log_both(f"     Gold SQL: {gold_sql}")
                log_both(f"     Pred SQL: {pred_sql}")
                correct += 1
            else:
                log_both(f"  ❌ FAIL in {elapsed:.1f}s (Retries: {retries})")
                log_both(f"     Gold SQL: {gold_sql}")
                log_both(f"     Pred SQL: {pred_sql}")
                if state.get("error_message"):
                    log_both(f"     Error: {state.get('error_message')}")
                else:
                    log_both(f"     Gold Rows (first 3): {gold_rows[:3]}")
                    log_both(f"     Pred Rows (first 3): {pred_rows[:3]}")
            log_both("-" * 80)

        acc = (correct / total) * 100 if total else 0
        val = (valid_sql / total) * 100 if total else 0
        avg_t = total_time / total if total else 0

        summary = (
            f"\n{'=' * 45}\n"
            f" AGENTIC PIPELINE EVALUATION SUMMARY\n"
            f"{'=' * 45}\n"
            f" Total Questions : {total}\n"
            f" Valid SQL %     : {val:.1f}%\n"
            f" Execution Acc % : {acc:.1f}%\n"
            f" Average Latency : {avg_t:.1f}s\n"
            f" Total Retries   : {total_retries}\n"
            f"{'=' * 45}\n"
        )
        log_both(summary)
        print(f"Detailed report saved to: {report_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Agentic Pipeline")
    parser.add_argument("--limit", type=int, help="Max questions to run")
    parser.add_argument("--category", type=str, help="Filter by category")
    args = parser.parse_args()

    run_evaluation(limit=args.limit, category=args.category)
