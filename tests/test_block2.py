import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from src.common.db import get_admin_engine, get_connector
from src.ingestion.build_domains import load_domains

pytestmark = pytest.mark.db

TABLES = [
    (schema, table, spec.source)
    for schema, dom in load_domains().items()
    for table, spec in dom.tables.items()
]

BLOCKED = [
    "INSERT INTO sales.orders (order_id) VALUES ('x')",
    "UPDATE sales.orders SET order_status = 'x'",
    "DELETE FROM sales.orders",
    "TRUNCATE sales.orders",
    "DROP TABLE sales.orders",
    "CREATE TABLE sales.hacked (id int)",
    "CREATE SCHEMA hacked",
    "ALTER TABLE sales.orders ADD COLUMN x int",
]


@pytest.mark.parametrize("schema,table,source", TABLES)
def test_domain_table_matches_raw(schema, table, source):
    with get_admin_engine().connect() as conn:
        new = conn.execute(text(f"SELECT count(*) FROM {schema}.{table}")).scalar_one()
        old = conn.execute(text(f"SELECT count(*) FROM raw.{source}")).scalar_one()
    assert new == old


def test_column_types_are_real():
    query = text(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema = :s AND table_name = :t AND column_name = :c"
    )
    with get_admin_engine().connect() as conn:
        ts = conn.execute(
            query, {"s": "sales", "t": "orders", "c": "order_purchase_timestamp"}
        ).scalar_one()
        price = conn.execute(
            query, {"s": "sales", "t": "order_items", "c": "price"}
        ).scalar_one()
    assert ts == "timestamp without time zone"
    assert price == "numeric"


def test_reader_can_select():
    result = get_connector().run_query("SELECT count(*) FROM sales.orders")
    assert result.rows[0][0] == 99441


def test_reader_role_settings():
    db = get_connector()
    assert db.run_query("SHOW statement_timeout").rows[0][0] == "30s"
    assert db.run_query("SHOW default_transaction_read_only").rows[0][0] == "on"


@pytest.mark.parametrize("sql", BLOCKED)
def test_reader_cannot_write(sql):
    with pytest.raises(DBAPIError):
        get_connector().run_query(sql)


def test_reader_cannot_see_raw():
    with pytest.raises(DBAPIError):
        get_connector().run_query("SELECT * FROM raw.orders LIMIT 1")


def test_reader_only_lists_domain_tables():
    tables = get_connector().list_tables(
        ["raw", "sales", "customer", "catalog", "marketing"]
    )
    assert len(tables) == 11
    assert all(schema != "raw" for schema, _ in tables)


def test_search_path_and_max_rows():
    db = get_connector()
    assert (
        db.run_query("SELECT count(*) FROM orders", search_path="sales").rows[0][0]
        == 99441
    )
    result = db.run_query("SELECT * FROM sales.orders", max_rows=5)
    assert result.row_count == 5 and result.truncated is True


def test_data_unchanged_after_attacks():
    with get_admin_engine().connect() as conn:
        assert (
            conn.execute(text("SELECT count(*) FROM sales.orders")).scalar_one()
            == 99441
        )
