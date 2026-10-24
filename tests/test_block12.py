"""Tests for Block 12: Baseline Text2SQL, AST Validator, Comparer, and Golden Set."""

from decimal import Decimal
import pytest
import yaml

from config.settings import PROJECT_ROOT
from src.adapters.db.base import ColumnInfo
from src.eval.comparer import compare_results
from src.text2sql.baseline.schema_context import format_schema_for_prompt
from src.text2sql.baseline.validator import validate_and_clean_sql


def test_validator_valid_select_appends_limit():
    res = validate_and_clean_sql("SELECT * FROM sales.orders")
    assert res.is_valid is True
    assert "LIMIT 100" in res.cleaned_sql
    assert res.tables == ["sales.orders"]


def test_validator_preserves_existing_limit():
    res = validate_and_clean_sql("SELECT * FROM sales.orders LIMIT 10")
    assert res.is_valid is True
    assert "LIMIT 10" in res.cleaned_sql
    assert "LIMIT 100" not in res.cleaned_sql


def test_validator_blocks_dml_and_ddl():
    assert validate_and_clean_sql("DROP TABLE sales.orders").is_valid is False
    assert validate_and_clean_sql("DELETE FROM sales.orders").is_valid is False
    assert (
        validate_and_clean_sql("INSERT INTO sales.orders VALUES (1)").is_valid is False
    )
    assert (
        validate_and_clean_sql("ALTER TABLE sales.orders ADD COLUMN x INT").is_valid
        is False
    )


def test_validator_blocks_modifying_cte():
    res = validate_and_clean_sql("WITH d AS (DELETE FROM sales.orders) SELECT 1")
    assert res.is_valid is False
    assert "Delete" in (res.error_message or "")


def test_validator_blocks_multiple_statements():
    res = validate_and_clean_sql("SELECT 1; SELECT 2")
    assert res.is_valid is False
    assert "Multiple statements" in (res.error_message or "")


def test_validator_extracts_markdown():
    res = validate_and_clean_sql("```sql\nSELECT * FROM catalog.products;\n```")
    assert res.is_valid is True
    assert "catalog.products" in res.tables


def test_comparer_tolerant_floats():
    g = [(1, "SP", 10.0001)]
    p = [(1, "sp ", Decimal("10.0002"))]
    assert compare_results(g, p) is True


def test_comparer_order_sensitivity():
    g = [(1,), (2,)]
    p = [(2,), (1,)]
    assert compare_results(g, p, order_sensitive=False) is True
    assert compare_results(g, p, order_sensitive=True) is False


def test_comparer_mismatched_row_counts():
    assert compare_results([(1,)], [(1,), (2,)]) is False


def test_format_schema_for_prompt():
    cols = [
        ColumnInfo("sales", "orders", "order_id", "text", False),
        ColumnInfo("sales", "orders", "order_status", "text", True),
    ]
    txt = format_schema_for_prompt(cols)
    assert "Table: sales.orders" in txt
    assert "order_id (text NOT NULL)" in txt
    assert "order_status (text NULL)" in txt


def test_golden_set_structure():
    path = PROJECT_ROOT / "config" / "golden_olist.yaml"
    assert path.exists()
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    qs = data.get("questions", [])
    assert len(qs) == 50
    ids = [q["id"] for q in qs]
    assert len(set(ids)) == 50
    for q in qs:
        assert "id" in q and "question" in q and "category" in q
