"""SQL Validator node for LangGraph workflow."""

from __future__ import annotations
from typing import Any
from src.text2sql.agents.state import AgentState
from src.text2sql.baseline.validator import validate_and_clean_sql

FORBIDDEN_SCHEMAS = {"raw", "dq", "meta", "app"}


def sql_validator_node(state: AgentState) -> dict[str, Any]:
    """Node: validates AST safety, permitted schemas, and LIMIT injection."""
    raw_sql = state.get("generated_sql")
    if not raw_sql:
        return {
            "is_valid_sql": False,
            "validation_errors": ["No SQL was generated."],
        }

    val = validate_and_clean_sql(raw_sql, default_limit=100)
    if not val.is_valid:
        return {
            "is_valid_sql": False,
            "validation_errors": [val.error_message or "Invalid SQL syntax."],
        }

    # Guardrail: check forbidden schemas
    for tbl in val.tables:
        if "." in tbl:
            schema_prefix = tbl.split(".", 1)[0].lower()
            if schema_prefix in FORBIDDEN_SCHEMAS:
                return {
                    "is_valid_sql": False,
                    "validation_errors": [
                        f"Access to internal schema '{schema_prefix}' is forbidden."
                    ],
                }

    return {
        "is_valid_sql": True,
        "generated_sql": val.cleaned_sql,
        "selected_tables": val.tables,
        "validation_errors": [],
    }


if __name__ == "__main__":
    from src.text2sql.agents.state import create_initial_state

    # Test safe query
    st1 = create_initial_state("test")
    st1["generated_sql"] = "SELECT * FROM sales.orders"
    print("Safe SQL validation:", sql_validator_node(st1))

    # Test forbidden schema
    st2 = create_initial_state("test")
    st2["generated_sql"] = "SELECT * FROM meta.tables"
    print("Forbidden schema validation:", sql_validator_node(st2))
