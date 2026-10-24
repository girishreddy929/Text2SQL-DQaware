"""AST validation and query sanitation using sqlglot."""

from __future__ import annotations
from dataclasses import dataclass
import sqlglot
from sqlglot import exp


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    cleaned_sql: str | None
    tables: list[str]
    error_message: str | None = None


FORBIDDEN_EXPRESSIONS = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Command,
    exp.Create,
)


def extract_sql_code(raw_text: str) -> str:
    """Extract SQL from markdown backticks or raw LLM output."""
    text = raw_text.strip()
    if "```sql" in text:
        text = text.split("```sql", 1)[1]
        text = text.split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1]
        text = text.split("```", 1)[0]
    return text.strip().rstrip(";")


def validate_and_clean_sql(
    raw_sql: str,
    dialect: str = "postgres",
    default_limit: int | None = 100,
) -> ValidationResult:
    """
    Validate that SQL is strictly SELECT (no DDL/DML, even in CTEs).
    Appends default_limit if provided and no existing LIMIT is found.
    """
    cleaned = extract_sql_code(raw_sql)
    if not cleaned:
        return ValidationResult(False, None, [], "Empty SQL query.")

    try:
        parsed_list = sqlglot.parse(cleaned, read=dialect)
    except Exception as exc:
        return ValidationResult(False, None, [], f"SQL syntax error: {exc}")

    if not parsed_list or parsed_list[0] is None:
        return ValidationResult(False, None, [], "Failed to parse SQL statement.")
    if len(parsed_list) > 1:
        return ValidationResult(
            False, None, [], "Multiple statements are not permitted."
        )

    expression = parsed_list[0]

    # Must be a SELECT expression (or Union of Selects)
    if not isinstance(expression, (exp.Select, exp.Union)):
        return ValidationResult(
            False,
            None,
            [],
            f"Statement must be SELECT, found {expression.key.upper()}.",
        )

    # Disallow DDL/DML anywhere in the AST (including within CTEs)
    for forbidden in FORBIDDEN_EXPRESSIONS:
        if expression.find(forbidden):
            return ValidationResult(
                False,
                None,
                [],
                f"Data-modifying statement '{forbidden.__name__}' is forbidden.",
            )

    # Extract all referenced tables: schema.table or bare table
    tables: list[str] = []
    for table_expr in expression.find_all(exp.Table):
        schema = table_expr.db
        table_name = table_expr.name
        full_name = f"{schema}.{table_name}" if schema else table_name
        if full_name not in tables:
            tables.append(full_name)

    # Inject LIMIT if absent and default_limit is requested
    if default_limit is not None and expression.find(exp.Limit) is None:
        expression = expression.limit(default_limit)

    final_sql = expression.sql(dialect=dialect)
    return ValidationResult(True, final_sql, tables)
