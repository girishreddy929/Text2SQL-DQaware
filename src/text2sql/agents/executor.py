"""Database Executor node for LangGraph workflow."""

from __future__ import annotations
from typing import Any
from src.adapters.db.base import DBConnector
from src.common.db import get_connector
from src.text2sql.agents.state import AgentState


def resolve_search_path(source_id: str) -> str | None:
    if source_id.startswith("bird:"):
        db_id = source_id.split(":", 1)[1]
        return f"bird_{db_id}"
    return None


def sql_executor_node(
    state: AgentState,
    connector: DBConnector | None = None,
) -> dict[str, Any]:
    """Node: executes validated SQL under t2s_reader with schema isolation."""
    if not state.get("is_valid_sql") or not state.get("generated_sql"):
        return {
            "execution_result": None,
            "column_names": None,
            "row_count": 0,
            "error_message": "SQL validation failed or SQL missing prior to execution.",
        }

    sql = state["generated_sql"]
    source_id = state.get("source_id", "olist")
    search_path = resolve_search_path(source_id)
    active_connector = connector or get_connector(read_only=True)

    try:
        qr = active_connector.run_query(sql, search_path=search_path)
        return {
            "execution_result": qr.rows,
            "column_names": qr.columns,
            "row_count": qr.row_count,
            "error_message": None,
        }
    except Exception as exc:
        return {
            "execution_result": None,
            "column_names": None,
            "row_count": 0,
            "error_message": str(exc),
        }


if __name__ == "__main__":
    from src.text2sql.agents.state import create_initial_state

    # Test valid execution
    st = create_initial_state("test")
    st["is_valid_sql"] = True
    st["generated_sql"] = "SELECT count(*) FROM sales.orders"
    res = sql_executor_node(st)
    print("Valid run:", res["row_count"], "row(s) |", res["execution_result"])

    # Test execution error handling
    st_err = create_initial_state("test")
    st_err["is_valid_sql"] = True
    st_err["generated_sql"] = "SELECT nonexistent_column FROM sales.orders"
    res_err = sql_executor_node(st_err)
    print("Error caught:", res_err["error_message"])
