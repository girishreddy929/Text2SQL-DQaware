"""Block 4 tests: rule models, compiler, judge (no DB) and runner behaviour (DB)."""

import sys

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from src.common.db import get_admin_engine, get_reader_engine
from src.dq import runner
from src.dq.rule_compiler import compile_rule, judge, row_predicate
from src.dq.rules_models import BAD_EXAMPLES, RULE_ADAPTER, load_rules
from src.dq.runner import execute_rule

ALL_TYPES = {
    "NON_NULL",
    "UNIQUENESS",
    "RANGE",
    "SET",
    "REGEX",
    "ROW_CONDITION",
    "TABLE_CONDITION",
    "SQL_ASSERTION",
}
KNOWN_FAILS = {
    "products_category_present",
    "products_category_translated",
    "reviews_comment_message_present",
    "closed_deals_company_known",
    "payments_installments_positive",
    "orders_data_is_recent",
}


def make(**fields):
    """Build a validated rule on sales.orders, overriding any field."""
    rule = RULE_ADAPTER.validate_python({"id": "t", "table": "sales.orders", **fields})
    rule.source_id = "test"
    return rule


# ---------------------------------------------------------------- no database needed


def test_yaml_rules_load_cover_all_types_and_have_unique_ids():
    rules = load_rules()
    assert len(rules) >= 41
    assert {r.type for r in rules} == ALL_TYPES
    assert len({r.id for r in rules}) == len(rules)


@pytest.mark.parametrize("raw", BAD_EXAMPLES, ids=[b["id"] for b in BAD_EXAMPLES])
def test_bad_rules_are_rejected(raw):
    with pytest.raises(ValidationError):
        RULE_ADAPTER.validate_python(raw)


def test_dimension_defaults_and_requirements():
    assert make(type="NON_NULL", column="x").dimension == "Completeness"
    assert make(type="UNIQUENESS", column="x").dimension == "Uniqueness"
    with pytest.raises(ValidationError):  # ROW_CONDITION has no default dimension
        make(type="ROW_CONDITION", expression="a > 1")


def test_uniqueness_column_shorthand_becomes_columns():
    assert make(type="UNIQUENESS", column="x").columns == ["x"]
    assert make(type="UNIQUENESS", columns=["a", "b"]).columns == ["a", "b"]


def test_every_yaml_rule_compiles():
    for r in load_rules():
        c = compile_rule(r)
        assert c.kind in {"row", "table", "assertion"}
        if c.kind == "row":
            assert "is_ok" in c.count_sql and "LIMIT 10" in c.failing_sql
        if c.kind == "table":
            assert c.failing_sql is None


def test_predicate_text_is_exact():
    r = make(type="RANGE", column="price", min_value=0, strict_min=True)
    assert row_predicate(r) == '("price" IS NULL OR ("price" > 0))'
    r = make(
        type="RANGE", column="price", min_value=0, strict_min=True, ignore_null=False
    )
    assert row_predicate(r) == 'COALESCE(("price" > 0), false)'
    assert row_predicate(make(type="NON_NULL", column="x")) == '"x" IS NOT NULL'
    u = row_predicate(make(type="UNIQUENESS", columns=["a", "b"]))
    assert 'PARTITION BY "a", "b"' in u and '"a" IS NULL OR "b" IS NULL' in u


def test_set_values_are_quoted_safely():
    pred = row_predicate(make(type="SET", column="name", values=["O'Neil"]))
    assert "'O''Neil'" in pred


def test_judge_uses_exact_thresholds():
    row_rule = make(type="NON_NULL", column="x", threshold=99.9)
    assert judge(row_rule, 1000, 999, 1) == (
        99.9,
        True,
    )  # exactly on the threshold passes
    assert judge(row_rule, 1000, 998, 2) == (99.8, False)
    assert judge(row_rule, 0, 0, 0) == (100.0, True)  # empty table: nothing violates
    table_rule = make(
        type="TABLE_CONDITION", dimension="Completeness", expression="count(*) > 1"
    )
    assert judge(table_rule, 1, 1, 0) == (100.0, True)
    assert judge(table_rule, 1, 0, 1) == (0.0, False)
    assertion = make(type="SQL_ASSERTION", dimension="Consistency", sql="select 1")
    assert judge(assertion, 10000, 9999, 1) == (99.99, False)  # one violation is enough


def test_dangerous_sql_in_rules_is_rejected():
    with pytest.raises(ValidationError):
        make(
            type="SQL_ASSERTION",
            dimension="Consistency",
            sql="DELETE FROM sales.orders",
        )
    with pytest.raises(ValidationError):
        make(type="SQL_ASSERTION", dimension="Consistency", sql="select 1; select 2")


# ---------------------------------------------------------------- database needed


def _scalar(sql, **params):
    with get_admin_engine().connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


@pytest.mark.db
def test_rule_tables_exist():
    n = _scalar(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'dq' "
        "AND table_name IN ('rules', 'scan_runs', 'results', 'latest_results')"
    )
    assert n == 4


@pytest.fixture(scope="module")
def olist_statuses():
    with get_admin_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT rule_id, status FROM dq.latest_results WHERE source_id = 'olist'"
            )
        ).all()
        enabled = conn.execute(
            text("SELECT count(*) FROM dq.rules WHERE source_id = 'olist' AND enabled")
        ).scalar_one()
    if not rows:
        pytest.skip("No completed olist scan. Run: python -m src.dq.runner")
    return dict(rows), enabled


@pytest.mark.db
def test_latest_scan_covers_every_enabled_rule_without_errors(olist_statuses):
    statuses, enabled = olist_statuses
    assert len(statuses) == enabled
    assert "error" not in set(statuses.values())


@pytest.mark.db
def test_known_failures_fail_and_a_clean_rule_passes(olist_statuses):
    statuses, _ = olist_statuses
    for rule_id in KNOWN_FAILS:
        assert statuses[rule_id] == "failed", rule_id
    assert statuses["orders_order_id_unique"] == "passed"


@pytest.mark.db
def test_failed_rule_stores_sample_rows():
    n = _scalar(
        "SELECT jsonb_array_length(sample_failures) FROM dq.latest_results "
        "WHERE source_id = 'olist' AND rule_id = 'products_category_translated'"
    )
    assert n == 2


@pytest.mark.db
def test_broken_rule_becomes_error_status_not_a_crash():
    res = execute_rule(
        get_reader_engine(), make(type="NON_NULL", column="no_such_column"), 30
    )
    assert res["status"] == "error" and res["passed"] is False
    assert "no_such_column" in res["error_message"]


@pytest.mark.db
def test_write_hidden_inside_a_rule_cannot_change_data():
    sql = (
        "WITH d AS (DELETE FROM sales.orders RETURNING order_id) SELECT order_id FROM d"
    )
    rule = make(
        type="SQL_ASSERTION", dimension="Consistency", sql=sql
    )  # passes validation
    before = _scalar("SELECT count(*) FROM sales.orders")
    res = execute_rule(get_reader_engine(), rule, 30)
    assert res["status"] == "error"
    assert _scalar("SELECT count(*) FROM sales.orders") == before


@pytest.mark.db
def test_end_to_end_scan_pass_fail_error_and_scan_continues(tmp_path, monkeypatch):
    (tmp_path / "t.yaml").write_text(
        "source_id: test_block4\nrules:\n"
        "  - {id: t_ok, table: sales.orders, column: order_id, type: NON_NULL}\n"
        "  - {id: t_fail, table: sales.orders, column: order_status, type: SET, values: [delivered]}\n"
        "  - {id: t_error, table: sales.orders, column: missing_col, type: NON_NULL}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys, "argv", ["runner", "--source", "test_block4", "--rules-dir", str(tmp_path)]
    )
    try:
        assert runner.main() == 0
        with get_admin_engine().connect() as conn:
            run = conn.execute(
                text(
                    "SELECT status, rules_total, rules_passed, rules_failed, rules_errored "
                    "FROM dq.scan_runs WHERE source_id = 'test_block4' ORDER BY started_at DESC LIMIT 1"
                )
            ).one()
            statuses = dict(
                conn.execute(
                    text(
                        "SELECT rule_id, status FROM dq.latest_results WHERE source_id = 'test_block4'"
                    )
                ).all()
            )
        assert tuple(run) == ("completed", 3, 1, 1, 1)
        assert statuses == {"t_ok": "passed", "t_fail": "failed", "t_error": "error"}
    finally:  # leave no test data behind
        with get_admin_engine().begin() as conn:
            conn.execute(
                text("DELETE FROM dq.scan_runs WHERE source_id = 'test_block4'")
            )
            conn.execute(text("DELETE FROM dq.rules WHERE source_id = 'test_block4'"))
