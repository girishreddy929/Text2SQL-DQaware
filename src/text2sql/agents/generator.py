"""SQL Generator agent node for LangGraph workflow."""

from __future__ import annotations
from typing import Any
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.common.llm import get_chat_model
from src.common.llm_guard import call_resilient
from src.text2sql.agents.state import AgentState, create_initial_state
from src.text2sql.baseline.schema_context import get_baseline_schema_context


class SqlGenerationOutput(BaseModel):
    reasoning: str = Field(description="Step-by-step rationale for the SQL structure")
    sql: str = Field(description="The executable PostgreSQL SELECT statement")
    tables_used: list[str] = Field(
        default_factory=list, description="Referenced tables"
    )


def get_target_schemas(source_id: str) -> list[str]:
    if source_id.startswith("bird:"):
        db_id = source_id.split(":", 1)[1]
        return [f"bird_{db_id}"]
    return ["sales", "customer", "catalog", "marketing"]


def build_generator_prompt(state: AgentState, schema_ctx: str) -> str:
    question = state.get("rewritten_question") or state["question"]
    lines = [
        f"TARGET DATABASE / SCHEMAS: {get_target_schemas(state.get('source_id', 'olist'))}",
        f"\nDATABASE SCHEMA:\n{schema_ctx}",
    ]
    if state.get("evidence"):
        lines.append(f"\nBUSINESS CONTEXT / EVIDENCE:\n{state['evidence']}")
    if state.get("resolved_terms"):
        lines.append("\nRESOLVED BUSINESS METRICS / ONTOLOGY:")
        for t in state["resolved_terms"]:
            lines.append(f"- {t.get('term_name')}: {t.get('sql_expression')}")
    lines.append(f"\nUSER QUESTION:\n{question}")
    return "\n".join(lines)


SYSTEM_PROMPT = """You are a senior PostgreSQL expert generating queries for TrustSQL.
RULES:
1. Generate strictly a SELECT query. Never use DML/DDL.
2. Fully qualify table names with schema (e.g., sales.orders, catalog.products).
3. If table or column names contain spaces, mixed cases, or keywords (e.g. 'order'), enclose them in double quotes.
4. Output your answer using the structured output format with reasoning, sql, and tables_used.
"""


def sql_generator_node(state: AgentState) -> dict[str, Any]:
    """Node: generate SQL from state context using structured output."""
    schemas = get_target_schemas(state.get("source_id", "olist"))
    schema_ctx = get_baseline_schema_context(schemas)
    prompt_content = build_generator_prompt(state, schema_ctx)

    model = get_chat_model(temperature=0.0)
    structured_model = model.with_structured_output(SqlGenerationOutput)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt_content),
    ]

    try:
        output: SqlGenerationOutput | None = call_resilient(
            structured_model.invoke, messages
        )
        if output is None:
            return {
                "generated_sql": None,
                "reasoning": "Failed to parse structured output.",
                "validation_errors": ["LLM returned empty structured response."],
                "is_valid_sql": False,
            }
        return {
            "generated_sql": output.sql.strip().rstrip(";"),
            "reasoning": output.reasoning,
            "selected_tables": output.tables_used,
            "validation_errors": [],
        }
    except Exception as exc:
        return {
            "generated_sql": None,
            "reasoning": f"Exception during generation: {exc}",
            "validation_errors": [str(exc)],
            "is_valid_sql": False,
        }


if __name__ == "__main__":
    st = create_initial_state("How many products have weight greater than 500g?")
    result = sql_generator_node(st)
    print("Generated SQL:", result["generated_sql"])
    print("Reasoning:", result["reasoning"])
    print("Tables:", result["selected_tables"])
