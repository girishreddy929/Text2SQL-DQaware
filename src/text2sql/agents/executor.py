# src/text2sql/agents/executor.py
from sqlalchemy import text
from src.common.db import get_reader_engine
from src.common.logging import get_logger

logger = get_logger(__name__)


def resolve_search_path(source_id: str) -> str:
    """Determines the correct search_path based on the source_id."""
    if source_id.startswith("bird:"):
        db_id = source_id.split(":")[1]
        return f"bird_{db_id}"
    return "public"


def sql_executor_node(state: dict, connector=None) -> dict:
    """Executes the validated SQL against the database."""
    sql = state.get("generated_sql")
    source_id = state.get("source_id", "olist")

    if not sql:
        return {"error_message": "No SQL to execute."}

    logger.info(f"Executing SQL for source '{source_id}'...")

    engine = get_reader_engine()
    search_path = resolve_search_path(source_id)

    try:
        with engine.connect() as conn:
            # Set search path for BIRD databases
            if search_path != "public":
                conn.execute(text(f"SET LOCAL search_path = {search_path}"))

            # Execute query
            res = conn.execute(text(sql))

            # FIX: Use .mappings() to return a list of dicts, not tuples
            rows = [dict(row) for row in res.mappings()]

            # Extract column names from the first row if available
            cols = list(rows[0].keys()) if rows else []

            logger.info(f"Execution successful. Returned {len(rows)} rows.")
            return {
                "execution_result": rows,
                "column_names": cols,
                "row_count": len(rows),
                "error_message": "",
            }

    except Exception as e:
        err_msg = str(e)
        logger.error(f"Execution failed: {err_msg}")
        return {"error_message": err_msg, "execution_result": [], "row_count": 0}
