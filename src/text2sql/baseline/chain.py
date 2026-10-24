"""Baseline Text2SQL chain: Prompt -> Gemini -> AST Validation -> Execution."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from langchain_core.messages import HumanMessage

from config.settings import PROJECT_ROOT
from src.adapters.db.base import DBConnector, QueryResult
from src.common.db import get_connector
from src.common.llm import get_chat_model, response_text
from src.common.llm_guard import call_resilient
from src.text2sql.baseline.schema_context import get_baseline_schema_context
from src.text2sql.baseline.validator import validate_and_clean_sql


@dataclass
class BaselineResult:
    question: str
    generated_sql: str | None
    is_valid: bool
    tables_used: list[str]
    row_count: int
    error: str | None = None
    elapsed_ms: float = 0.0
    query_result: QueryResult | None = None


def load_prompt_template() -> str:
    path = PROJECT_ROOT / "prompts" / "baseline.txt"
    return path.read_text(encoding="utf-8")


def run_baseline(
    question: str,
    schemas: list[str] | None = None,
    default_limit: int | None = 100,
    connector: DBConnector | None = None,
) -> BaselineResult:
    """Run baseline query generation, validation, and read-only execution."""
    t0 = time.perf_counter()
    active_connector = connector or get_connector(read_only=True)
    schema_ctx = get_baseline_schema_context(schemas, connector=active_connector)
    prompt_text = load_prompt_template().format(
        schema_context=schema_ctx,
        question=question,
    )

    model = get_chat_model()
    resp = call_resilient(model.invoke, [HumanMessage(content=prompt_text)])
    raw_text = response_text(resp)

    val = validate_and_clean_sql(raw_text, default_limit=default_limit)
    if not val.is_valid:
        elapsed = (time.perf_counter() - t0) * 1000.0
        return BaselineResult(
            question=question,
            generated_sql=val.cleaned_sql,
            is_valid=False,
            tables_used=val.tables,
            row_count=0,
            error=val.error_message,
            elapsed_ms=round(elapsed, 2),
        )

    try:
        qr = active_connector.run_query(val.cleaned_sql)
        elapsed = (time.perf_counter() - t0) * 1000.0
        return BaselineResult(
            question=question,
            generated_sql=val.cleaned_sql,
            is_valid=True,
            tables_used=val.tables,
            row_count=qr.row_count,
            elapsed_ms=round(elapsed, 2),
            query_result=qr,
        )
    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000.0
        return BaselineResult(
            question=question,
            generated_sql=val.cleaned_sql,
            is_valid=True,
            tables_used=val.tables,
            row_count=0,
            error=str(exc),
            elapsed_ms=round(elapsed, 2),
        )


if __name__ == "__main__":
    demo_q = "How many total orders are in the database?"
    res = run_baseline(demo_q)
    print(f"Question: {res.question}")
    print(f"Generated SQL: {res.generated_sql}")
    print(
        f"Valid: {res.is_valid} | Row count: {res.row_count} | Elapsed: {res.elapsed_ms}ms"
    )
    if res.query_result and res.query_result.rows:
        print(f"Answer: {res.query_result.rows[0]}")
    if res.error:
        print(f"Error: {res.error}")
