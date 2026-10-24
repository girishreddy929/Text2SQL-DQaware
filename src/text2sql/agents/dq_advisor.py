# src/text2sql/agents/dq_advisor.py
"""Data Quality Advisor agent: produces dynamic, dimension-aware business advisories."""

from typing import Any
from sqlalchemy import text

from src.common.db import get_reader_engine
from src.common.logging import get_logger
from src.text2sql.agents.state import AgentState

logger = get_logger("text2sql.agents.dq_advisor")

FAILING_RULES_SQL = """
SELECT r.table_name, r.column_names, r.rule_type, r.dimension, r.pass_pct, r.rule_id
FROM dq.latest_results r
WHERE r.source_id = :source_id
  AND r.table_name = ANY(:tables)
  AND r.status = 'failed'
ORDER BY r.pass_pct ASC
LIMIT 3;
"""

NULL_PROFILES_SQL = """
SELECT table_name, column_name, null_pct
FROM dq.latest_profiles
WHERE source_id = :source_id
  AND table_name = ANY(:tables)
  AND null_pct >= 1.0
ORDER BY null_pct DESC
LIMIT 3;
"""


def format_rule_advisory(
    table: str, cols: list[str] | None, dim: str, rule_type: str, pass_pct: float
) -> str:
    """Dynamically converts technical rule scan metrics into executive business advisories."""
    col_str = f"'{cols[0]}'" if cols and len(cols) == 1 else "key columns"
    t_name = table.title()
    pct = f"{pass_pct:.1f}%"

    dim_upper = (dim or "").upper()
    if dim_upper == "TIMELINESS":
        return f"[{t_name} - Freshness] Historical data window check on {col_str} is only {pct} compliant; data may be outdated."
    elif dim_upper == "COMPLETENESS":
        return f"[{t_name} - Completeness] Completeness threshold not met on {col_str} ({pct} populated)."
    elif dim_upper == "UNIQUENESS":
        return f"[{t_name} - Integrity] Duplicate records detected in {col_str} ({pct} unique)."
    elif dim_upper == "VALIDITY":
        return f"[{t_name} - Data Validity] Values in {col_str} deviate from expected domain rules ({pct} valid)."
    elif dim_upper == "CONSISTENCY":
        return f"[{t_name} - Consistency] Cross-table consistency check failed on {col_str} ({pct} aligned)."
    else:
        return f"[{t_name} - Quality] Quality scan on {col_str} failed with {pct} pass rate."


def extract_table_names(state: AgentState) -> list[str]:
    """Extracts bare table names from state and generated SQL."""
    tables = list(state.get("selected_tables", []))
    sql = state.get("generated_sql", "").lower()

    for known in [
        "orders",
        "order_items",
        "order_payments",
        "order_reviews",
        "products",
        "customers",
        "frpm",
        "satscores",
        "schools",
    ]:
        if known in sql and known not in tables:
            tables.append(known)

    return list({t.split(".")[-1] for t in tables})


def dq_advisor_node(state: AgentState, engine=None) -> dict[str, Any]:
    """LangGraph node: dynamically generates dimension-aware data quality advisories."""
    source_id = state.get("source_id", "olist")
    tables = extract_table_names(state)

    if not tables:
        return {"dq_warnings": []}

    reader = engine or get_reader_engine()
    warnings: list[str] = []

    try:
        with reader.connect() as conn:
            # 1. Dimension-driven rule advisories (fully dynamic)
            rule_rows = conn.execute(
                text(FAILING_RULES_SQL), {"source_id": source_id, "tables": tables}
            ).fetchall()
            for r in rule_rows:
                warnings.append(
                    format_rule_advisory(
                        r.table_name,
                        r.column_names,
                        r.dimension,
                        r.rule_type,
                        float(r.pass_pct),
                    )
                )

            # 2. Notable null percentages (fully dynamic)
            null_rows = conn.execute(
                text(NULL_PROFILES_SQL), {"source_id": source_id, "tables": tables}
            ).fetchall()
            for n in null_rows:
                warnings.append(
                    f"[{n.table_name.title()} - Completeness] Column '{n.column_name}' has {float(n.null_pct):.1f}% missing values."
                )

    except Exception as exc:
        logger.warning("DQ Advisor lookup failed: %s", exc)

    logger.info(
        "Generated %d dynamic DQ advisory note(s) for tables %s", len(warnings), tables
    )
    return {"dq_warnings": warnings[:4]}


if __name__ == "__main__":
    print("\n--- Testing Dynamic, Generic DQ Advisor ---")
    mock_state: AgentState = {
        "source_id": "olist",
        "selected_tables": ["orders", "products"],
        "generated_sql": "SELECT order_id, product_category_name FROM sales.orders JOIN catalog.products USING (product_id)",
    }  # type: ignore

    out = dq_advisor_node(mock_state)
    for w in out["dq_warnings"]:
        print(f"Notice: {w}")
