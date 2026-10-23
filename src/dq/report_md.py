"""Pure Markdown builder for the DQ report (no database).

Demo: python -m src.dq.report_md
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Mapping, Sequence

from src.dq.scoring import Score, Scorecard, band, build_scorecard, row

FENCE = "`" * 3
NOTE = (
    "Scores are plain averages of rule pass %, rounded to 2 decimals, so a rule that fails "
    "at 99.998% can still show 100.00 inside a group. Exact numbers are in Findings."
)
SCORE_HEADERS = ["Name", "Score", "Band", "Rules passed"]


def cell(x: Any) -> str:
    return str(x).replace("|", "\\|").replace("\n", " ")


def md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines += ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def score_rows(scores: list[Score]) -> list[list[Any]]:
    return [[s.name, s.score, band(s.score), f"{s.passed}/{s.rules}"] for s in scores]


def finding(i: int, f: Mapping) -> str:
    cols = ", ".join(f.get("column_names") or []) or "(table level)"
    out = [
        f"### {i}. `{f['rule_id']}`: {f['schema_name']}.{f['table_name']} ({f['dimension']})",
        f"- Pass rate **{Decimal(str(f['pass_pct'])):.4f}%** (threshold {f['threshold']}%); "
        f"{f['failed_rows']:,} failing rows of {f['total_rows']:,}",
        f"- Rule type {f['rule_type']}; columns: {cols}",
    ]
    if f.get("description"):
        out.append(f"- What it checks: {f['description']}")
    samples = f.get("sample_failures") or []
    if isinstance(samples, str):
        samples = json.loads(samples)
    if samples:
        text = json.dumps(samples[:2], default=str)[:300].replace("`", "'")
        out.append(f"- Example failing rows: `{text}`")
    if f.get("failing_sql"):
        out += [
            "",
            "<details><summary>SQL that lists the failing rows</summary>",
            "",
            FENCE + "sql",
            f["failing_sql"].strip(),
            FENCE,
            "",
            "</details>",
        ]
    return "\n".join(out)


def build_report(
    source: str,
    card: Scorecard,
    failing: list[Mapping],
    null_columns: list[Mapping],
    coverage: Mapping,
    scanned_at: Any,
    profiled_at: Any,
) -> str:
    o = card.overall
    parts = [
        f"# Data Quality Report: {source}",
        "",
        f"- Rules scanned: {scanned_at} | Data profiled: {profiled_at}",
        f"- **Overall score {o.score} ({band(o.score)})**; {o.passed} of {o.rules} rules passed",
        f"- Errored rules (not scored): {', '.join(card.errored) or 'none'}",
        "",
        "## Scores by dimension",
        "",
        md_table(SCORE_HEADERS, score_rows(card.dimensions)),
        "",
        "## Scores by table (worst first)",
        "",
        md_table(SCORE_HEADERS, score_rows(card.tables)),
        "",
        f"_{NOTE}_",
        "",
        f"## Findings ({len(failing)} failing rules)",
        "",
    ]
    parts += [finding(i, f) + "\n" for i, f in enumerate(failing, 1)] or [
        "No failing rules.",
        "",
    ]
    null_rows = [
        [
            f"{c['schema_name']}.{c['table_name']}",
            c["column_name"],
            f"{Decimal(str(c['null_pct'])):.2f}",
            f"{c['null_count']:,}",
            f"{c['row_count']:,}",
        ]
        for c in null_columns
    ]
    cols, covered = coverage["columns"], coverage["columns_with_rules"]
    share = 100 * covered / cols if cols else 0
    parts += [
        "## Columns with the most missing values",
        "",
        md_table(["Table", "Column", "Null %", "Nulls", "Rows"], null_rows),
        "",
        "## Rule coverage",
        "",
        f"- Tables profiled: {coverage['tables']} (with at least one rule: {coverage['tables_with_rules']})",
        f"- Columns profiled: {cols}; with at least one rule: {covered} ({share:.1f}%)",
        "",
        "## How scores are calculated",
        "",
        "- Rule score = % of rows that pass the rule (`pass_pct`).",
        "- Group score (dimension, table, overall) = plain average of its rule scores.",
        "- Errored rules are not scored. Bands: Good >= 99, Fair >= 95, otherwise Poor.",
    ]
    return "\n".join(parts) + "\n"


def main() -> int:
    card = build_scorecard(
        [
            row("orders_id_not_null", "sales.orders", "Completeness", "100", "passed"),
            row("orders_data_is_recent", "sales.orders", "Timeliness", "0", "failed"),
            row(
                "products_category_present",
                "catalog.products",
                "Completeness",
                "98.1487",
                "failed",
            ),
        ]
    )
    failing = [
        {
            "rule_id": "products_category_present",
            "schema_name": "catalog",
            "table_name": "products",
            "dimension": "Completeness",
            "rule_type": "NON_NULL",
            "threshold": 99,
            "pass_pct": "98.1487",
            "failed_rows": 610,
            "total_rows": 32951,
            "column_names": ["product_category_name"],
            "description": "Product category should be filled",
            "sample_failures": [{"product_id": "a1", "product_category_name": None}],
            "failing_sql": "SELECT t.* FROM catalog.products t WHERE t.product_category_name IS NULL",
        }
    ]
    nulls = [
        {
            "schema_name": "marketing",
            "table_name": "closed_deals",
            "column_name": "has_company",
            "null_pct": "92.5178",
            "null_count": 779,
            "row_count": 842,
        }
    ]
    cov = {
        "tables": 11,
        "tables_with_rules": 10,
        "columns": 70,
        "columns_with_rules": 35,
    }
    print(build_report("olist", card, failing, nulls, cov, "demo-scan", "demo-profile"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
