# src/text2sql/agents/generator.py
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from src.common.llm import get_chat_model
from src.common.logging import get_logger
from src.common.db import get_connector

logger = get_logger(__name__)


class SqlGenerationOutput(BaseModel):
    reasoning: str = Field(description="Step-by-step reasoning for the SQL query.")
    sql: str = Field(description="The generated PostgreSQL query.")
    tables_used: list[str] = Field(
        description="List of tables used in the query, e.g., ['schema.table']."
    )


def get_target_schemas(source_id: str) -> list[str]:
    if source_id == "olist":
        return ["sales", "customer", "catalog", "marketing"]
    elif source_id.startswith("bird:"):
        return [f"bird_{source_id.split(':')[1]}"]
    return ["public"]


def build_targeted_schema_context(source_id: str, selected_tables: list[str]) -> str:
    schemas = get_target_schemas(source_id)
    connector = get_connector(read_only=True)

    try:
        all_cols = connector.list_columns(schemas)
    finally:
        connector.close()

    tables_dict = {}
    for col in all_cols:
        table_key = f"{col.schema}.{col.table}"
        if not selected_tables or table_key in selected_tables:
            if table_key not in tables_dict:
                tables_dict[table_key] = []
            tables_dict[table_key].append(f"{col.column} ({col.data_type})")

    lines = []
    for t, cols in tables_dict.items():
        lines.append(f"Table: {t}")
        lines.append(f"Columns: {', '.join(cols)}")
        lines.append("")

    return "\n".join(lines)


def build_generator_prompt(state: dict, schema_ctx: str) -> ChatPromptTemplate:
    sys_msg = """You are an expert PostgreSQL developer.
Write a syntactically correct PostgreSQL query to answer the user's question.

Target Schema:
{schema_ctx}

{join_path}

{ontology_ctx}

{evidence_ctx}

Rules:
1. Return ONLY a valid SELECT statement.
2. Always use fully qualified table names (schema.table).
3. Always double-quote column names if they contain spaces or special characters.
4. Use the provided join paths if joining tables.
5. Use the provided ontology formulas for business metrics.
"""

    ontology_ctx = ""
    if state.get("resolved_terms"):
        ontology_ctx = "Business Metrics & Ontology:\n"
        for term in state["resolved_terms"]:
            ontology_ctx += f"- {term['term_name']}: {term['sql_expression']}\n"

    evidence_ctx = ""
    if state.get("evidence"):
        evidence_ctx = f"External Evidence/Hints:\n{state['evidence']}\n"

    join_path = state.get("join_path", "")
    if join_path:
        join_path = f"Join Paths:\n{join_path}\n"

    return ChatPromptTemplate.from_messages(
        [("system", sys_msg), ("user", "Question: {question}")]
    ).partial(
        schema_ctx=schema_ctx,
        ontology_ctx=ontology_ctx,
        evidence_ctx=evidence_ctx,
        join_path=join_path,
    )


def sql_generator_node(state: dict) -> dict:
    question = state.get("rewritten_question") or state.get("question")
    source_id = state.get("source_id")
    selected_tables = state.get("selected_tables", [])

    logger.info(f"Generating SQL for: '{question}' using tables: {selected_tables}")

    schema_ctx = build_targeted_schema_context(source_id, selected_tables)
    prompt = build_generator_prompt(state, schema_ctx)

    llm = get_chat_model(temperature=0.0).with_structured_output(SqlGenerationOutput)
    chain = prompt | llm

    try:
        result = chain.invoke({"question": question})
        if result:
            logger.info(f"Generated SQL: {result.sql}")
            return {
                "generated_sql": result.sql,
                "reasoning": result.reasoning,
                "selected_tables": result.tables_used,
            }
    except Exception as e:
        logger.error(f"SQL Generation failed: {e}")
        return {"error_message": f"Generation failed: {str(e)}"}

    return {"error_message": "Failed to generate SQL."}
