"""Block 5 tests: recommender, scoring, report. Run: pytest tests/test_block5.py -v"""

import re
import sys
from decimal import Decimal

import pytest

from src.dq.recommender import recommend_all, recommend_column, sample
from src.dq.report_md import build_report, md_table
from src.dq.rules_models import RULE_ADAPTER
from src.dq.scoring import band, build_scorecard, row


def of_type(suggestions, rule_type):
    return [s for s in suggestions if s.rule["type"] == rule_type]


def make_card():
    return build_scorecard(
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


FAILING = {
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
    "description": "Category is filled",
    "sample_failures": [],
    "failing_sql": "SELECT 1",
}
COVERAGE = {"tables": 1, "tables_with_rules": 1, "columns": 2, "columns_with_rules": 1}
VALUES = [
    {"value": "a", "count": 90},
    {"value": "b", "count": 9},
    {"value": "c", "count": 1},
]


# ---------- recommender (no database) ----------
def test_clean_column_gets_high_confidence_not_null():
    rule = of_type(
        recommend_column(sample("sales", "orders", "order_status", "text", 1000, 0, 3)),
        "NON_NULL",
    )[0]
    assert rule.rule["threshold"] == 100 and rule.confidence == "high"


def test_null_threshold_is_floor_of_pass_rate():
    s = recommend_column(
        sample("catalog", "products", "product_category_name", "text", 32951, 610, 73)
    )
    assert of_type(s, "NON_NULL")[0].rule["threshold"] == 98


def test_tiny_and_mostly_null_columns_are_skipped():
    assert recommend_column(sample("a", "t", "x_id", "text", 10, 0, 10)) == []
    assert recommend_column(sample("a", "t", "c", "text", 1000, 900, 5)) == []


def test_uniqueness_needs_an_id_like_name():
    assert of_type(
        recommend_column(sample("a", "t", "order_id", "text", 1000, 0, 1000)),
        "UNIQUENESS",
    )
    price = sample("a", "t", "price", "numeric", 1000, 0, 1000, min_value="1")
    assert not of_type(recommend_column(price), "UNIQUENESS")


def test_set_rule_needs_values_that_cover_every_row():
    ok = of_type(
        recommend_column(
            sample("a", "t", "state", "text", 100, 0, 3, top_values=VALUES)
        ),
        "SET",
    )
    assert ok[0].rule["values"] == ["a", "b", "c"] and ok[0].confidence == "medium"
    partial = VALUES[:2] + [{"value": "c", "count": 0}]  # covers 99 of 100 rows
    assert not of_type(
        recommend_column(
            sample("a", "t", "state", "text", 100, 0, 3, top_values=partial)
        ),
        "SET",
    )


def test_rare_value_lowers_confidence():
    tv = [
        {"value": "a", "count": 9990},
        {"value": "b", "count": 9},
        {"value": "c", "count": 1},
    ]
    s = of_type(
        recommend_column(sample("a", "t", "state", "text", 10000, 0, 3, top_values=tv)),
        "SET",
    )
    assert s[0].confidence == "low"


def test_range_only_for_non_negative_numbers():
    assert not of_type(
        recommend_column(
            sample("a", "t", "amt", "numeric", 100, 0, 50, min_value="-3")
        ),
        "RANGE",
    )
    assert of_type(
        recommend_column(sample("a", "t", "amt", "numeric", 100, 0, 50, min_value="0")),
        "RANGE",
    )


def test_fixed_length_id_gets_a_regex():
    p = sample("a", "t", "order_id", "text", 100, 0, 100, min_length=32, max_length=32)
    assert of_type(recommend_column(p), "REGEX")[0].rule["pattern"] == "^.{32}$"


def test_suggestions_are_valid_rules_with_clean_unique_ids():
    odd = "Percent (%) Eligible Free (K-12)"
    profiles = [
        sample(
            "bird_california_schools",
            "frpm",
            odd,
            "numeric",
            1000,
            0,
            500,
            min_value="0",
        ),
        sample(
            "bird_california_schools",
            "frpm",
            "Percent Eligible Free K 12",
            "numeric",
            1000,
            0,
            500,
            min_value="0",
        ),
        sample(
            "sales",
            "orders",
            "order_id",
            "text",
            1000,
            0,
            1000,
            min_length=32,
            max_length=32,
        ),
    ]
    suggestions = recommend_all(profiles)
    ids = [s.rule["id"] for s in suggestions]
    assert len(ids) == len(set(ids))  # slug collisions get _2, _3
    for s in suggestions:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", s.rule["id"])
        RULE_ADAPTER.validate_python(s.rule)


# ---------- scoring and report builder (no database) ----------
def test_scores_match_hand_calculation():
    card = make_card()
    assert (card.overall.score, card.overall.passed, card.overall.rules) == (
        Decimal("67.60"),
        3,
        6,
    )
    scores = {s.name: s.score for s in card.dimensions}
    assert scores["Completeness"] == Decimal("76.41")
    assert [s.name for s in card.dimensions] == [
        "Completeness",
        "Validity",
        "Timeliness",
    ]
    assert card.tables[0].name == "marketing.closed_deals"  # worst first


def test_errored_rules_are_listed_not_scored():
    card = make_card()
    assert card.errored == ["broken_rule"]
    assert card.overall.rules == 6  # 7 results, 1 errored


def test_bands():
    assert [band(Decimal(x)) for x in ("99", "98.99", "95", "94.99")] == [
        "Good",
        "Fair",
        "Fair",
        "Poor",
    ]
    assert band(None) == "n/a"


def test_empty_results_give_no_score():
    empty = build_scorecard([])
    assert (
        empty.overall.score is None and empty.tables == [] and empty.worst_rules == []
    )


def test_report_without_failures():
    text = build_report("olist", make_card(), [], [], COVERAGE, "scan", "profile")
    assert "No failing rules." in text and "Overall score 67.60 (Poor)" in text


def test_report_shows_exact_rate_and_sql():
    text = build_report(
        "olist", make_card(), [FAILING], [], COVERAGE, "scan", "profile"
    )
    assert "98.1487%" in text and "<details>" in text and "`" * 3 + "sql" in text


def test_pipe_in_a_table_cell_is_escaped():
    assert "x\\|y" in md_table(["a"], [["x|y"]])


# ---------- against the database ----------
@pytest.mark.db
def test_scorecard_equals_independent_sql():
    from src.dq.score_run import card_scores, independent_scores, load_results

    assert card_scores(build_scorecard(load_results("olist"))) == independent_scores(
        "olist"
    )


@pytest.mark.db
def test_report_generation_end_to_end(tmp_path, monkeypatch):
    from src.dq import report

    out = tmp_path / "r.md"
    monkeypatch.setattr(sys, "argv", ["report", "--source", "olist", "--out", str(out)])
    assert report.main() == 0  # includes the report's own self-check
    content = out.read_text(encoding="utf-8")
    assert "payments_installments_positive" in content and "Overall score" in content


@pytest.mark.db
def test_olist_suggestions_are_valid_rules():
    from src.dq.recommend_run import load_profiles

    suggestions = recommend_all(load_profiles("olist"))
    assert len(suggestions) > 50
    for s in suggestions:
        RULE_ADAPTER.validate_python(s.rule)


@pytest.mark.db
def test_bird_california_profile_is_stored():
    from sqlalchemy import text
    from src.common.db import get_admin_engine

    sql = text(
        "SELECT count(*) FROM dq.latest_profiles WHERE source_id = 'bird:california_schools'"
    )
    with get_admin_engine().connect() as conn:
        assert conn.execute(sql).scalar_one() == 89
