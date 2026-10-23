"""Pure scoring maths for DQ results (no database).

Rule score = pass_pct. Group score = plain average of its rule scores (equal weight).
Errored rules are not scored, only listed.
Demo: python -m src.dq.scoring
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Mapping

DIMENSIONS = (
    "Completeness",
    "Uniqueness",
    "Validity",
    "Consistency",
    "Timeliness",
    "Accuracy",
)
CENT = Decimal("0.01")
GOOD, FAIR = Decimal("99"), Decimal("95")


@dataclass(frozen=True)
class Score:
    name: str
    score: Decimal | None  # None when nothing was scored
    rules: int  # rules that were scored
    passed: int  # of those, rules whose verdict is passed


@dataclass
class Scorecard:
    overall: Score
    dimensions: list[Score]  # in standard dimension order
    tables: list[Score]  # worst first
    table_dimensions: dict[tuple[str, str], Score]  # (schema.table, dimension) -> Score
    errored: list[str]  # rule ids that could not run
    worst_rules: list[tuple[str, Decimal]]  # failing rules, lowest pass % first


def band(score: Decimal | None) -> str:
    if score is None:
        return "n/a"
    if score >= GOOD:
        return "Good"
    return "Fair" if score >= FAIR else "Poor"


def average(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return (sum(values, Decimal(0)) / len(values)).quantize(
        CENT, rounding=ROUND_HALF_UP
    )


def score_group(name: str, rows: list[Mapping]) -> Score:
    pcts = [Decimal(str(r["pass_pct"])) for r in rows]
    return Score(name, average(pcts), len(rows), sum(1 for r in rows if r["passed"]))


def table_of(r: Mapping) -> str:
    return f"{r['schema_name']}.{r['table_name']}"


def group_by(rows: list[Mapping], key) -> dict:
    groups: dict = {}
    for r in rows:
        groups.setdefault(key(r), []).append(r)
    return groups


def dimension_order(name: str) -> tuple[int, str]:
    return (DIMENSIONS.index(name) if name in DIMENSIONS else len(DIMENSIONS), name)


def build_scorecard(results: Iterable[Mapping]) -> Scorecard:
    """results = rows of dq.latest_results (needs rule_id, schema_name, table_name,
    dimension, pass_pct, passed, status)."""
    results = list(results)
    scored = [
        r for r in results if r["status"] != "error" and r["pass_pct"] is not None
    ]
    errored = sorted(r["rule_id"] for r in results if r["status"] == "error")
    by_dim = group_by(scored, lambda r: r["dimension"])
    by_table = group_by(scored, table_of)
    by_both = group_by(scored, lambda r: (table_of(r), r["dimension"]))
    tables = sorted(
        (score_group(n, g) for n, g in by_table.items()),
        key=lambda s: (s.score, s.name),
    )
    failing = sorted(
        (
            (r["rule_id"], Decimal(str(r["pass_pct"])))
            for r in scored
            if not r["passed"]
        ),
        key=lambda x: (x[1], x[0]),
    )
    return Scorecard(
        overall=score_group("overall", scored),
        dimensions=[
            score_group(n, by_dim[n]) for n in sorted(by_dim, key=dimension_order)
        ],
        tables=tables,
        table_dimensions={
            k: score_group(f"{k[0]} / {k[1]}", g) for k, g in by_both.items()
        },
        errored=errored,
        worst_rules=failing,
    )


def row(rule_id, table, dim, pct, status):
    """Build a fake dq.latest_results row for the demo."""
    schema, name = table.split(".")
    return {
        "rule_id": rule_id,
        "schema_name": schema,
        "table_name": name,
        "dimension": dim,
        "pass_pct": None if pct is None else Decimal(pct),
        "passed": status == "passed",
        "status": status,
    }


def show(s: Score) -> None:
    print(
        f"  {s.name:32} {str(s.score):>6}  {band(s.score):5} {s.passed}/{s.rules} rules passed"
    )


def main() -> int:
    card = build_scorecard(
        [
            row("orders_id_not_null", "sales.orders", "Completeness", "100", "passed"),
            row(
                "orders_delivered_has_date",
                "sales.orders",
                "Completeness",
                "99.9920",
                "passed",
            ),
            row("orders_data_is_recent", "sales.orders", "Timeliness", "0", "failed"),
            row(
                "products_category_present",
                "catalog.products",
                "Completeness",
                "98.1487",
                "failed",
            ),
            row(
                "products_weight_positive",
                "catalog.products",
                "Validity",
                "99.9879",
                "passed",
            ),
            row(
                "closed_deals_company_known",
                "marketing.closed_deals",
                "Completeness",
                "7.4821",
                "failed",
            ),
            row("broken_rule", "sales.orders", "Validity", None, "error"),
        ]
    )
    print("Overall:")
    show(card.overall)
    print("Dimensions:")
    [show(s) for s in card.dimensions]
    print("Tables (worst first):")
    [show(s) for s in card.tables]
    print("Errored rules:", card.errored)
    print("Failing rules (lowest first):", [(i, str(p)) for i, p in card.worst_rules])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
