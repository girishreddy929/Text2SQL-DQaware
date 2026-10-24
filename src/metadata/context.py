"""Pure builders of the facts text sent to the LLM. Demo: python -m src.metadata.context"""

import json
import re
from typing import Mapping, Sequence

from src.dq.profiler_sql import qi

TOP_SHOWN = 6
VALUE_CHARS = 30
CHUNK_SIZE = 40
PII_NAME = re.compile(
    r"(e?mail|phone|fax|cpf|ssn|passport|birth|dob|first_?name|last_?name|"
    r"fname|lname|full_?name|address|street|zip|postal)",
    re.I,
)


def pii_hint(column: str) -> bool:
    """True when the column NAME looks personal (a hint only; the LLM decides too)."""
    return bool(PII_NAME.search(column))


def short(value, limit: int = VALUE_CHARS) -> str:
    text = str(value).replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def pct(x) -> str:
    return f"{float(x or 0):.1f}%"


def top_values_of(p: Mapping) -> list[dict]:
    tv = p.get("top_values") or []
    return json.loads(tv) if isinstance(tv, str) else list(tv)


def column_line(p: Mapping) -> str:
    parts = [
        f"{qi(p['column_name'])} {p['data_type']}",
        f"nulls {pct(p['null_pct'])}",
        f"distinct {p['distinct_count']}",
    ]
    if (
        p.get("type_category") in ("numeric", "temporal")
        and p.get("min_value") is not None
    ):
        parts.append(f"range {short(p['min_value'])} .. {short(p['max_value'])}")
    top = top_values_of(p)[:TOP_SHOWN]
    if top:
        parts.append(
            "top: " + ", ".join(f"{short(t['value'])} ({pct(t['pct'])})" for t in top)
        )
    if pii_hint(p["column_name"]):
        parts.append("NAME-LOOKS-PERSONAL")
    return " | ".join(parts)


def chunk_profiles(
    profiles: Sequence[Mapping], size: int = CHUNK_SIZE
) -> list[list[Mapping]]:
    ordered = sorted(profiles, key=lambda p: p["ordinal_position"])
    return [ordered[i : i + size] for i in range(0, len(ordered), size)]


def build_table_context(
    schema: str, table: str, row_count: int, profiles: Sequence[Mapping]
) -> str:
    lines = [f"Table {qi(schema)}.{qi(table)} ({row_count:,} rows)", "Columns:"]
    lines += [
        f"- {column_line(p)}"
        for p in sorted(profiles, key=lambda p: p["ordinal_position"])
    ]
    return "\n".join(lines)


def main() -> None:
    demo = [
        {
            "column_name": "order_id",
            "data_type": "text",
            "type_category": "text",
            "ordinal_position": 1,
            "null_pct": 0,
            "distinct_count": 99441,
            "min_value": None,
            "max_value": None,
            "top_values": None,
        },
        {
            "column_name": "order_status",
            "data_type": "text",
            "type_category": "text",
            "ordinal_position": 2,
            "null_pct": 0,
            "distinct_count": 8,
            "min_value": None,
            "max_value": None,
            "top_values": [
                {"value": "delivered", "count": 96478, "pct": 97.02},
                {"value": "shipped", "count": 1107, "pct": 1.11},
            ],
        },
        {
            "column_name": "customer_email",
            "data_type": "text",
            "type_category": "text",
            "ordinal_position": 3,
            "null_pct": 1.8,
            "distinct_count": 500,
            "min_value": None,
            "max_value": None,
            "top_values": [],
        },
        {
            "column_name": "price",
            "data_type": "numeric",
            "type_category": "numeric",
            "ordinal_position": 4,
            "null_pct": 0,
            "distinct_count": 5968,
            "min_value": "0.85",
            "max_value": "6735.00",
            "top_values": [],
        },
    ]
    print(build_table_context("sales", "orders", 99441, demo))
    print("\nchunks of 3:", [len(c) for c in chunk_profiles(demo, 3)])


if __name__ == "__main__":
    main()
