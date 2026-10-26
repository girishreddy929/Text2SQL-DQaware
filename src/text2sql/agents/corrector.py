# src/text2sql/agents/corrector.py
"""Error Corrector agent node for LangGraph workflow."""

from __future__ import annotations
from typing import Any
from langchain_core.messages import HumanMessage, SystemMessage

from src.common.llm import get_chat_model
from src.common.llm_guard import call_resilient
from src.text2sql.agents.generator import (
    SqlGenerationOutput,
    get_target_schemas,
)
from src.text2sql.agents.state import AgentState
from src.text2sql.baseline.schema_context import get_baseline_schema_context

CORRECTOR_SYSTEM_PROMPT = """You are a senior PostgreSQL debugging specialist for TrustSQL.
A previously generated query failed to validate or execute.
Your task is to fix the SQL query using the exact error message and database schema provided.

RULES:
1. Generate strictly a valid SELECT query. Never use DML/DDL.
2. Fully qualify table names with schema (e.g. sales.orders).
3. If identifiers contain special characters or mixed case, enclose them in double quotes.
4. Output your corrected answer using the structured output format with reasoning and sql.
"""


def build_corrector_prompt(state: AgentState, schema_ctx: str) -> str:
    question = state.get("rewritten_question") or state["question"]
    failed_sql = state.get("generated_sql", "None")

    # FIX: Safely build the errors list whether validation_errors is a string or list
    errors = []
    val_errs = state.get("validation_errors")
    if val_errs:
        if isinstance(val_errs, list):
            errors.extend(val_errs)
        else:
            errors.append(str(val_errs))

    if state.get("error_message"):
        errors.append(str(state["error_message"]))

    error_summary = (
        "\n".join(f"- {e}" for e in errors) if errors else "Unknown execution error."
    )

    return (
        f"USER QUESTION:\n{question}\n\n"
        f"FAILED SQL QUERY:\n{failed_sql}\n\n"
        f"ERROR(S) ENCOUNTERED:\n{error_summary}\n\n"
        f"DATABASE SCHEMA CONTEXT:\n{schema_ctx}\n"
    )


def sql_corrector_node(state: AgentState) -> dict[str, Any]:
    """Node: diagnose error, increment retry count, and generate repaired SQL."""
    current_retry = state.get("retry_count", 0) + 1
    schemas = get_target_schemas(state.get("source_id", "olist"))
    schema_ctx = get_baseline_schema_context(schemas)
    prompt_content = build_corrector_prompt(state, schema_ctx)

    model = get_chat_model(temperature=0.0)
    structured_model = model.with_structured_output(SqlGenerationOutput)
    messages = [
        SystemMessage(content=CORRECTOR_SYSTEM_PROMPT),
        HumanMessage(content=prompt_content),
    ]

    try:
        output: SqlGenerationOutput | None = call_resilient(
            structured_model.invoke, messages
        )
        if output is None:
            return {
                "retry_count": current_retry,
                "is_valid_sql": False,
                "validation_errors": [
                    "Corrector failed to produce structured response."
                ],
            }
        return {
            "generated_sql": output.sql.strip().rstrip(";"),
            "reasoning": f"[Retry {current_retry}] {output.reasoning}",
            "selected_tables": output.tables_used,
            "retry_count": current_retry,
            "error_message": None,
            "validation_errors": "",
            "is_valid_sql": True,
        }
    except Exception as exc:
        return {
            "retry_count": current_retry,
            "is_valid_sql": False,
            "error_message": f"Exception in corrector: {exc}",
        }


if __name__ == "__main__":
    from src.text2sql.agents.state import create_initial_state

    st = create_initial_state()
    st["question"] = "How many orders exist?"
    st["generated_sql"] = "SELECT count(*) FROM sales.nonexistent_orders_table"
    st["error_message"] = 'relation "sales.nonexistent_orders_table" does not exist'
    repaired = sql_corrector_node(st)
    print("Repaired SQL:", repaired.get("generated_sql"))
    print("Retry Count:", repaired.get("retry_count"))
    print("Reasoning:", repaired.get("reasoning"))
