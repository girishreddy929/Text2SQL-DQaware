"""Pure rule recommender: one dq.profiles row -> suggested DQ rules (no DB access).

Demo: python -m src.dq.recommender
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from math import floor
from typing import Any, Mapping

MIN_ROWS = 20  # skip tiny tables
MAX_NULL_PCT = Decimal("10")  # above this, no NON_NULL suggestion
MAX_SET_VALUES = 10  # profiler keeps top_n = 10 values
MAX_VALUE_CHARS = 60
RARE_SHARE = Decimal("0.001")  # a value under 0.1% of rows may be a typo
MIN_FIXED_LENGTH = 8

ID_LOWER = re.compile(r"(^|_)id$|^id_|key$|code$", re.IGNORECASE)
ID_CAMEL = re.compile(r"[a-z](ID|Id)$")  # CustomerID, UserId (case-sensitive)


@dataclass(frozen=True)
class Suggestion:
    rule: dict[str, Any]  # same fields as a YAML rule
    confidence: str  # high | medium | low
    reason: str  # why we suggest it (shown in the report)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_") or "x"


def is_id_like(name: str) -> bool:
    return bool(ID_LOWER.search(name) or ID_CAMEL.search(name))


def number(text: Any) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def make_rule(
    p: Mapping,
    kind: str,
    rule_type: str,
    threshold: int,
    description: str,
    **extra: Any,
) -> dict[str, Any]:
    parts = (p["schema_name"], p["table_name"], p["column_name"])
    return {
        "id": "rec_" + "_".join(slug(x) for x in parts) + "_" + kind,
        "table": f"{p['schema_name']}.{p['table_name']}",
        "type": rule_type,
        "column": p["column_name"],
        "threshold": threshold,
        "description": description,
        "enabled": True,
        **extra,
    }


def suggest_non_null(p: Mapping) -> list[Suggestion]:
    col, rows, nulls = p["column_name"], p["row_count"], p["null_count"]
    if nulls == 0:
        rule = make_rule(p, "not_null", "NON_NULL", 100, f"{col} is never null")
        return [Suggestion(rule, "high", f"0 nulls in {rows} rows")]
    pct = Decimal(str(p["null_pct"]))
    if pct > MAX_NULL_PCT:
        return []
    thr = floor(100 - pct)
    rule = make_rule(p, "not_null", "NON_NULL", thr, f"{col} is at least {thr}% filled")
    return [Suggestion(rule, "medium", f"{nulls} nulls ({pct:.2f}%) in {rows} rows")]


def suggest_unique(p: Mapping) -> list[Suggestion]:
    col, pct = p["column_name"], p.get("distinct_pct")
    if pct is None or Decimal(str(pct)) < 100 or not is_id_like(col):
        return []
    rule = make_rule(
        p, "unique", "UNIQUENESS", 100, f"{col} identifies a row (no duplicates)"
    )
    return [
        Suggestion(
            rule, "high", f"all {p['distinct_count']} non-null values are distinct"
        )
    ]


def suggest_set(p: Mapping) -> list[Suggestion]:
    distinct, non_null = p["distinct_count"], p["row_count"] - p["null_count"]
    tv = p.get("top_values") or []
    if isinstance(tv, str):
        tv = json.loads(tv)
    if (
        p["type_category"] != "text"
        or not 2 <= distinct <= MAX_SET_VALUES
        or len(tv) != distinct
    ):
        return []
    values = [t["value"] for t in tv]
    if any(v is None or len(str(v)) > MAX_VALUE_CHARS for v in values):
        return []
    if sum(t["count"] for t in tv) != non_null:  # top values must cover every row
        return []
    rarest = min(t["count"] for t in tv)
    rare = Decimal(rarest) / Decimal(non_null) < RARE_SHARE
    rule = make_rule(
        p,
        "allowed_values",
        "SET",
        100,
        f"{p['column_name']} only holds the {distinct} known values",
        values=[str(v) for v in values],
    )
    reason = f"{distinct} distinct values cover every non-null row"
    if rare:
        reason += f"; rarest value has only {rarest} rows (typo?)"
    return [Suggestion(rule, "low" if rare else "medium", reason)]


def suggest_range(p: Mapping) -> list[Suggestion]:
    lo, col = number(p.get("min_value")), p["column_name"]
    if p["type_category"] != "numeric" or lo is None or lo < 0 or is_id_like(col):
        return []
    rule = make_rule(
        p, "non_negative", "RANGE", 100, f"{col} is never negative", min_value=0
    )
    return [Suggestion(rule, "medium", f"minimum observed value is {p['min_value']}")]


def suggest_length(p: Mapping) -> list[Suggestion]:
    n, col = p.get("min_length"), p["column_name"]
    if (
        p["type_category"] != "text"
        or not is_id_like(col)
        or n is None
        or n != p.get("max_length")
        or n < MIN_FIXED_LENGTH
    ):
        return []
    rule = make_rule(
        p,
        "length",
        "REGEX",
        100,
        f"{col} always has {n} characters",
        pattern=f"^.{{{n}}}$",
    )
    return [Suggestion(rule, "medium", f"every value has exactly {n} characters")]


CHECKS = (suggest_non_null, suggest_unique, suggest_set, suggest_range, suggest_length)


def recommend_column(p: Mapping) -> list[Suggestion]:
    if p["row_count"] < MIN_ROWS or p["null_count"] == p["row_count"]:
        return []
    return [s for check in CHECKS for s in check(p)]


def recommend_all(profiles: list[Mapping]) -> list[Suggestion]:
    """All suggestions; ids made unique (suffix _2, _3) if slugs collide."""
    seen: dict[str, int] = {}
    out: list[Suggestion] = []
    for p in profiles:
        for s in recommend_column(p):
            rid = s.rule["id"]
            seen[rid] = seen.get(rid, 0) + 1
            if seen[rid] > 1:
                s = Suggestion(
                    {**s.rule, "id": f"{rid}_{seen[rid]}"}, s.confidence, s.reason
                )
            out.append(s)
    return out


def sample(
    schema, table, column, category, rows, nulls, distinct, **extra
) -> dict[str, Any]:
    """Build a fake dq.profiles row for the demo."""
    return {
        "schema_name": schema,
        "table_name": table,
        "column_name": column,
        "type_category": category,
        "row_count": rows,
        "null_count": nulls,
        "null_pct": Decimal(nulls) * 100 / rows,
        "distinct_count": distinct,
        "distinct_pct": Decimal(distinct) * 100 / (rows - nulls),
        "min_value": None,
        "max_value": None,
        "min_length": None,
        "max_length": None,
        "top_values": None,
        **extra,
    }


def main() -> int:
    from pydantic import ValidationError
    from src.dq.rules_models import RULE_ADAPTER

    status = [
        ("delivered", 96478),
        ("shipped", 1107),
        ("canceled", 625),
        ("unavailable", 609),
        ("invoiced", 314),
        ("processing", 301),
        ("created", 5),
        ("approved", 2),
    ]
    profiles = [
        sample(
            "sales",
            "orders",
            "order_id",
            "text",
            99441,
            0,
            99441,
            min_length=32,
            max_length=32,
        ),
        sample(
            "sales",
            "orders",
            "order_status",
            "text",
            99441,
            0,
            8,
            top_values=[{"value": v, "count": c} for v, c in status],
        ),
        sample("sales", "orders", "order_approved_at", "temporal", 99441, 160, 90733),
        sample("catalog", "products", "product_category_name", "text", 32951, 610, 73),
        sample(
            "sales",
            "order_items",
            "price",
            "numeric",
            112650,
            0,
            5968,
            min_value="0.85",
        ),
        sample(
            "marketing", "closed_deals", "has_company", "text", 842, 779, 1
        ),  # 92% null
        sample("catalog", "tiny_lookup", "lookup_id", "text", 10, 0, 10),  # too small
    ]
    suggestions, bad = recommend_all(profiles), 0
    for s in suggestions:
        r = s.rule
        try:
            RULE_ADAPTER.validate_python(r)
            ok = "ok"
        except ValidationError as exc:
            ok, bad = "INVALID", bad + 1
            print(exc)
        print(
            f"{ok:7} {s.confidence:6} {r['id']:46} {r['type']:10} thr={r['threshold']:<3} {s.reason}"
        )
    print(
        f"\n{len(suggestions)} suggestions, {bad} invalid (has_company and tiny_lookup give none)"
    )
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
