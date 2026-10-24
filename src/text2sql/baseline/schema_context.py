"""Extracts and formats raw schema context for baseline Text2SQL prompts."""

from __future__ import annotations
from collections import defaultdict
from src.adapters.db.base import DBConnector, ColumnInfo
from src.common.db import get_connector


def format_schema_for_prompt(columns: list[ColumnInfo]) -> str:
    """Format column metadata into a clean table schema listing."""
    tables: dict[str, list[ColumnInfo]] = defaultdict(list)
    for col in columns:
        full_table = f"{col.schema}.{col.table}"
        tables[full_table].append(col)

    lines: list[str] = []
    for full_table in sorted(tables.keys()):
        cols = tables[full_table]
        lines.append(f"Table: {full_table}")
        for c in cols:
            nullable_str = " NULL" if c.is_nullable else " NOT NULL"
            lines.append(f"  - {c.column} ({c.data_type}{nullable_str})")
        lines.append("")
    return "\n".join(lines).strip()


def get_baseline_schema_context(
    schemas: list[str] | None = None,
    connector: DBConnector | None = None,
) -> str:
    """
    Fetch column metadata using t2s_reader and format into text context.
    Defaults to Olist domain schemas if schemas is not specified.
    """
    active_schemas = schemas or ["sales", "customer", "catalog", "marketing"]
    active_connector = connector or get_connector(read_only=True)
    columns = active_connector.list_columns(active_schemas)
    return format_schema_for_prompt(columns)


if __name__ == "__main__":
    context = get_baseline_schema_context()
    print(f"Generated schema context: {len(context.splitlines())} lines")
    print("\n--- Preview (first 12 lines) ---")
    print("\n".join(context.splitlines()[:12]))
