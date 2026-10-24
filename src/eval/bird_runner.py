"""Evaluation runner for the BIRD benchmark on PostgreSQL."""

from __future__ import annotations
import argparse
import time

from langchain_core.messages import HumanMessage
from config.settings import get_settings
from src.adapters.db.base import DBConnector
from src.common.db import get_connector
from src.common.llm import get_chat_model, response_text
from src.common.llm_guard import call_resilient
from src.eval.bird_cache import (
    FreeTierThrottler,
    load_eval_cache,
    make_cache_key,
    save_eval_cache,
)
from src.eval.bird_sampler import get_bird_sample
from src.eval.comparer import compare_results
from src.text2sql.baseline.chain import load_prompt_template
from src.text2sql.baseline.schema_context import get_baseline_schema_context
from src.text2sql.baseline.validator import validate_and_clean_sql


def run_bird_question(
    q: dict,
    with_evidence: bool,
    connector: DBConnector,
    throttler: FreeTierThrottler,
    cache: dict[str, str],
) -> dict:
    qid = q["question_id"]
    db_id = q["db_id"]
    schema = f"bird_{db_id}"
    gold_sql = q["SQL"]
    diff = q.get("difficulty", "moderate")
    question_text = q["question"]
    if with_evidence and q.get("evidence"):
        question_text += f"\nEVIDENCE: {q['evidence']}"

    settings = get_settings()
    ckey = make_cache_key(qid, with_evidence, settings.gemini_chat_model)
    t0 = time.perf_counter()
    cached = ckey in cache

    if cached:
        raw_sql = cache[ckey]
    else:
        throttler.wait_if_needed()
        schema_ctx = get_baseline_schema_context([schema], connector=connector)
        prompt = load_prompt_template().format(
            schema_context=schema_ctx, question=question_text
        )
        model = get_chat_model()
        resp = call_resilient(model.invoke, [HumanMessage(content=prompt)])
        raw_sql = response_text(resp)
        cache[ckey] = raw_sql
        save_eval_cache(cache)

    val = validate_and_clean_sql(raw_sql, default_limit=None)
    lat_ms = (time.perf_counter() - t0) * 1000.0

    if not val.is_valid:
        return {
            "id": qid,
            "diff": diff,
            "valid": False,
            "match": False,
            "cached": cached,
            "ms": lat_ms,
            "err": val.error_message,
        }

    try:
        gold_qr = connector.run_query(gold_sql, search_path=schema)
        pred_qr = connector.run_query(val.cleaned_sql, search_path=schema)
        order_sens = "order by" in gold_sql.lower()
        matched = compare_results(
            gold_qr.rows, pred_qr.rows, order_sensitive=order_sens
        )
        return {
            "id": qid,
            "diff": diff,
            "valid": True,
            "match": matched,
            "cached": cached,
            "ms": lat_ms,
            "err": None,
        }
    except Exception as exc:
        return {
            "id": qid,
            "diff": diff,
            "valid": True,
            "match": False,
            "cached": cached,
            "ms": lat_ms,
            "err": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run BIRD benchmark evaluation.")
    parser.add_argument(
        "--limit", type=int, default=5, help="Number of questions (default: 5)"
    )
    parser.add_argument(
        "--all", action="store_true", help="Run full 100 sample questions"
    )
    parser.add_argument(
        "--no-evidence", action="store_true", help="Disable evidence hints"
    )
    parser.add_argument("--db", type=str, default=None, help="Filter by db_id")
    args = parser.parse_args()

    questions = get_bird_sample(target_count=100)
    if args.db:
        questions = [q for q in questions if q["db_id"] == args.db]
    if not args.all and args.limit:
        questions = questions[: args.limit]

    with_evidence = not args.no_evidence
    print(
        f"=== BIRD Benchmark Eval: {len(questions)} Qs (evidence={with_evidence}) ==="
    )
    connector = get_connector(read_only=True)
    throttler = FreeTierThrottler(min_interval_seconds=4.2)
    cache = load_eval_cache()
    results = []

    for q in questions:
        r = run_bird_question(q, with_evidence, connector, throttler, cache)
        status = "PASS" if r["match"] else "FAIL"
        c_flag = "[CACHE]" if r["cached"] else "[LIVE] "
        print(
            f"[{status}] Q{r['id']:<4} ({r['diff']:<11}) {c_flag} {r['ms']:.0f}ms {r['err'] or ''}"
        )
        results.append(r)

    total = len(results)
    correct = sum(1 for r in results if r["match"])
    valid = sum(1 for r in results if r["valid"])
    print("\n" + "=" * 50)
    print(f"Total Evaluated:    {total}")
    print(f"Valid SQL:          {valid}/{total} ({valid / total * 100:.1f}%)")
    print(f"Execution Accuracy: {correct}/{total} ({correct / total * 100:.1f}%)")
    for d in ("simple", "moderate", "challenging"):
        sub = [r for r in results if r["diff"] == d]
        if sub:
            c = sum(1 for r in sub if r["match"])
            print(f"  - {d:<11}:     {c}/{len(sub)} ({c / len(sub) * 100:.1f}%)")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
