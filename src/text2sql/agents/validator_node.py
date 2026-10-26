# src/text2sql/agents/validator_node.py
from src.common.logging import get_logger
from src.text2sql.baseline.validator import validate_and_clean_sql

logger = get_logger(__name__)

FORBIDDEN_SCHEMAS = ["raw", "dq", "meta", "app"]


def sql_validator_node(state: dict) -> dict:
    """Validates the generated SQL for safety and syntax."""
    sql = state.get("generated_sql", "")

    if not sql:
        return {
            "is_valid_sql": False,
            "validation_errors": "No SQL generated.",
            "error_message": "No SQL generated.",
        }

    # Disable LIMIT injection if we are in evaluation mode
    eval_mode = state.get("eval_mode", False)
    default_limit = None if eval_mode else 100

    val_result = validate_and_clean_sql(
        sql, dialect="postgres", default_limit=default_limit
    )

    if not val_result.is_valid:
        logger.warning(f"SQL Validation failed: {val_result.error_message}")
        return {
            "is_valid_sql": False,
            "validation_errors": val_result.error_message,
            "error_message": f"Validation Error: {val_result.error_message}",
        }

    # Check for forbidden schemas
    for table in val_result.tables:
        schema = table.split(".")[0].lower() if "." in table else "public"
        if schema in FORBIDDEN_SCHEMAS:
            msg = f"Access to internal schema '{schema}' is forbidden."
            logger.warning(msg)
            return {
                "is_valid_sql": False,
                "validation_errors": msg,
                "error_message": f"Security Error: {msg}",
            }

    logger.info("SQL Validation passed.")
    return {
        "is_valid_sql": True,
        "generated_sql": val_result.cleaned_sql,
        "validation_errors": "",
        "error_message": "",
    }
