import pytest
from sqlalchemy import text

from src.common.db import get_admin_engine
from src.ingestion.load_raw import TABLES

pytestmark = pytest.mark.db


def _scalar(sql: str):
    with get_admin_engine().connect() as conn:
        return conn.execute(text(sql)).scalar_one()


@pytest.mark.parametrize("table,expected", list(TABLES.values()))
def test_row_counts(table, expected):
    assert _scalar(f"SELECT count(*) FROM raw.{table}") == expected


def test_all_raw_columns_are_text():
    bad = _scalar(
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_schema = 'raw' AND data_type <> 'text'"
    )
    assert bad == 0, "raw must stay untouched: every column TEXT"


def test_orders_order_id_is_unique():
    assert _scalar("SELECT count(DISTINCT order_id) FROM raw.orders") == 99441


def test_known_dq_issues_are_visible():
    # Real-world mess must survive loading; the DQ engine (Blocks 3-5) will measure it.
    assert (
        _scalar(
            "SELECT count(*) FROM raw.orders WHERE order_delivered_customer_date IS NULL"
        )
        > 0
    )
    assert (
        _scalar("SELECT count(*) FROM raw.products WHERE product_category_name IS NULL")
        > 0
    )
