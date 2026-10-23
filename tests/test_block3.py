"""Block 3 tests: profiler SQL builders (no DB needed) and the stored Olist profile (DB)."""

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from src.common.db import get_admin_engine, get_reader_engine
from src.dq.profile_verify import verify_column
from src.dq.profiler import run_generated
from src.dq.profiler_sql import (
    ColumnRef,
    ColumnStats,
    ProfilerConfig,
    build_stats_sql,
    build_top_values_sql,
    category_of,
    chunk_columns,
    format_top_values,
    load_profiler_config,
    parse_stats,
    qi,
    wants_top_values,
)

# ---------------------------------------------------------------- no database needed


def test_qi_quotes_and_escapes():
    assert qi("Academic Year") == '"Academic Year"'
    assert qi('a"b') == '"a""b"'


def test_category_of():
    assert category_of("integer") == "numeric"
    assert category_of("double precision") == "numeric"
    assert category_of("character varying") == "text"
    assert category_of("timestamp without time zone") == "temporal"
    assert category_of("boolean") == "boolean"
    assert category_of("bytea") == "other"


def test_stats_sql_quotes_odd_names():
    cols = [ColumnRef("Percent (%) Eligible", "double precision", 1)]
    sql = build_stats_sql("bird_x", "Table Name", cols)
    assert '"Percent (%) Eligible"' in sql
    assert 'FROM "bird_x"."Table Name"' in sql


def test_stats_sql_counts_only_for_other_types():
    sql = build_stats_sql("s", "t", [ColumnRef("blob", "bytea", 1)])
    assert "c1_nonnull" in sql
    assert "c1_distinct" not in sql and "c1_min" not in sql


def test_each_category_gets_its_own_statistics():
    cols = [
        ColumnRef("n", "integer", 1),
        ColumnRef("t", "text", 2),
        ColumnRef("d", "date", 3),
    ]
    sql = build_stats_sql("s", "t", cols)
    assert 'avg("n")::double precision AS c1_mean' in sql
    assert 'stddev_samp("n")' in sql
    assert 'length("n")' not in sql  # no string lengths for numbers
    assert 'min(length("t")) AS c2_minlen' in sql
    assert 'avg("t")' not in sql  # no mean for text
    assert 'min("d")::text AS c3_min' in sql
    assert 'avg("d")' not in sql and 'length("d")' not in sql


def test_chunk_columns():
    cols = [ColumnRef(f"c{i}", "text", i) for i in range(1, 8)]
    assert [len(c) for c in chunk_columns(cols, 3)] == [3, 3, 1]


def test_parse_stats_computes_percentages():
    cols = [ColumnRef("x", "text", 1)]
    row = {
        "row_count": 200,
        "c1_nonnull": 150,
        "c1_distinct": 50,
        "c1_min": "a",
        "c1_max": "z",
        "c1_minlen": 1,
        "c1_maxlen": 3,
        "c1_avglen": 2.0,
    }
    s = parse_stats(cols, row)[0]
    assert s.null_count == 50
    assert s.null_pct == 25.0
    assert s.distinct_pct == round(50 * 100 / 150, 4)
    assert (s.min_value, s.max_value, s.max_length) == ("a", "z", 3)


def _stats(category, row_count, null_count, distinct):
    return ColumnStats(
        name="c",
        position=1,
        data_type="x",
        category=category,
        row_count=row_count,
        null_count=null_count,
        null_pct=0.0,
        distinct_count=distinct,
    )


def test_wants_top_values_rules():
    cfg = ProfilerConfig()
    assert wants_top_values(_stats("text", 100, 0, 5), cfg) is True
    assert wants_top_values(_stats("text", 100, 0, 100), cfg) is False  # all unique
    assert wants_top_values(_stats("temporal", 100, 0, 5), cfg) is False  # category off
    assert wants_top_values(_stats("text", 100, 100, 0), cfg) is False  # all null
    assert (
        wants_top_values(_stats("text", 100, 0, None), cfg) is False
    )  # no distinct info


def test_format_top_values_uses_percent_of_all_rows():
    out = format_top_values([("a", 50), ("b", 25)], 100)
    assert out == [
        {"value": "a", "count": 50, "pct": 50.0},
        {"value": "b", "count": 25, "pct": 25.0},
    ]


def test_profiler_config_defaults_and_validation():
    cfg = ProfilerConfig()
    assert cfg.top_n == 10 and cfg.max_columns_per_query == 50
    assert load_profiler_config().top_n >= 1
    with pytest.raises(ValidationError):
        ProfilerConfig(top_n=0)
    with pytest.raises(ValidationError):
        ProfilerConfig(top_values_categories=["nonsense"])


def test_top_values_sql_shape():
    sql = build_top_values_sql(
        "sales", "orders", "order_status", ProfilerConfig(top_n=5)
    )
    assert sql.endswith("LIMIT 5")
    assert 'WHERE "order_status" IS NOT NULL' in sql
    assert 'FROM "sales"."orders"' in sql


# ---------------------------------------------------------------- database needed


@pytest.fixture(scope="module")
def latest_run():
    with get_admin_engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT run_id, tables_profiled, columns_profiled FROM dq.profile_runs "
                "WHERE source_id = 'olist' AND status = 'completed' "
                "ORDER BY started_at DESC LIMIT 1"
            )
        ).one_or_none()
    if row is None:
        pytest.skip("No completed olist profile run. Run: python -m src.dq.profiler")
    return {"run_id": str(row[0]), "tables": row[1], "columns": row[2]}


@pytest.mark.db
def test_latest_run_covers_every_olist_column(latest_run):
    with get_admin_engine().connect() as conn:
        expected = conn.execute(
            text(
                "SELECT count(*) FROM information_schema.columns c "
                "JOIN information_schema.tables t ON t.table_schema = c.table_schema "
                "AND t.table_name = c.table_name WHERE t.table_type = 'BASE TABLE' "
                "AND c.table_schema IN ('sales', 'customer', 'catalog', 'marketing')"
            )
        ).scalar_one()
        stored = conn.execute(
            text("SELECT count(*) FROM dq.profiles WHERE run_id = CAST(:r AS uuid)"),
            {"r": latest_run["run_id"]},
        ).scalar_one()
    assert latest_run["tables"] == 11
    assert latest_run["columns"] == expected == stored


@pytest.mark.db
def test_orders_delivery_nulls_match_independent_count(latest_run):
    with get_admin_engine().connect() as conn:
        stored = conn.execute(
            text(
                "SELECT null_count FROM dq.profiles WHERE run_id = CAST(:r AS uuid) "
                "AND schema_name = 'sales' AND table_name = 'orders' "
                "AND column_name = 'order_delivered_customer_date'"
            ),
            {"r": latest_run["run_id"]},
        ).scalar_one()
        fresh = conn.execute(
            text(
                "SELECT count(*) FROM sales.orders WHERE order_delivered_customer_date IS NULL"
            )
        ).scalar_one()
    assert stored == fresh
    assert fresh > 0  # the DQ story of this dataset: delivery dates have nulls


@pytest.mark.db
def test_stored_stats_sql_is_runnable(latest_run):
    with get_admin_engine().connect() as conn:
        stats_sql, row_count = conn.execute(
            text(
                "SELECT stats_sql, row_count FROM dq.profile_tables "
                "WHERE run_id = CAST(:r AS uuid) AND schema_name = 'sales' "
                "AND table_name = 'orders'"
            ),
            {"r": latest_run["run_id"]},
        ).one()
        row = run_generated(conn, stats_sql).mappings().one()
    assert row["row_count"] == row_count


@pytest.mark.db
def test_verifier_passes_for_orders(latest_run):
    cfg = load_profiler_config()
    with get_admin_engine().connect() as conn:
        profiles = (
            conn.execute(
                text(
                    "SELECT * FROM dq.profiles WHERE run_id = CAST(:r AS uuid) "
                    "AND schema_name = 'sales' AND table_name = 'orders' ORDER BY ordinal_position"
                ),
                {"r": latest_run["run_id"]},
            )
            .mappings()
            .all()
        )
        assert len(profiles) == 8
        for p in profiles:
            checks, bad = verify_column(conn, p, cfg)
            assert checks > 0 and not bad, bad


@pytest.mark.db
def test_reader_cannot_read_dq():
    with get_reader_engine().connect() as conn:
        with pytest.raises(DBAPIError):
            conn.execute(text("SELECT 1 FROM dq.profiles"))


@pytest.mark.db
def test_percent_and_colon_in_identifiers_are_escaped():
    with get_admin_engine().connect() as conn:
        result = run_generated(conn, 'SELECT 1 AS "Percent (%) a:b", 2::int AS "x"')
        assert list(result.keys()) == ["Percent (%) a:b", "x"]
