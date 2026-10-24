"""tests/test_block9.py: Unit and integration tests for Knowledge Graph."""

from __future__ import annotations

import networkx as nx
import pytest
from sqlalchemy import text
from src.adapters.db.base import ColumnInfo
from src.common.db import get_admin_engine
from src.metadata.kg_builder import build_kg_entities
from src.metadata.kg_graph import find_join_path, format_join_sql, load_graph
from src.metadata.kg_infer import is_candidate_pair
from src.metadata.kg_models import JoinCandidate, edge_id, node_id


# --- Unit Tests (No DB) ---


def test_node_and_edge_id_format():
    nid = node_id("olist", "table", "sales.orders")
    assert nid == "olist:table:sales.orders"
    eid = edge_id("olist", "contains", nid, "olist:column:sales.orders.order_id")
    assert "->" in eid
    assert eid.startswith("olist:contains:")


def test_candidate_pair_heuristics():
    c1 = ColumnInfo("sales", "orders", "customer_id", "text", False)
    c2 = ColumnInfo("customer", "customers", "customer_id", "text", False)
    c_diff = ColumnInfo("customer", "customers", "phone", "text", False)
    assert is_candidate_pair(c1, c2) is True
    assert is_candidate_pair(c1, c_diff) is False
    assert is_candidate_pair(c1, c1) is False


def test_pure_kg_builder():
    domains = {"sales": ["sales.orders"]}
    tables = [{"schema_name": "sales", "table_name": "orders", "description": "orders"}]
    cols = [
        {
            "schema_name": "sales",
            "table_name": "orders",
            "column_name": "id",
            "data_type": "text",
            "is_pii": False,
        }
    ]
    rules = [
        {
            "rule_id": "r1",
            "schema_name": "sales",
            "table_name": "orders",
            "column_names": ["id"],
            "rule_type": "NON_NULL",
        }
    ]
    joins = [
        JoinCandidate("sales.orders", "sales.items", "id", "order_id", 100.0, "test")
    ]

    nodes, edges = build_kg_entities("test", domains, tables, cols, rules, joins)
    assert len(nodes) == 4  # 1 domain + 1 table + 1 col + 1 rule
    assert len(edges) == 5  # contains + has_column + has_dq_rule + 2 joins_with


def test_shortest_join_path_mock():
    G = nx.DiGraph()
    n_a, n_b = "t:table:a", "t:table:b"
    G.add_node(n_a, name="a")
    G.add_node(n_b, name="b")
    G.add_edge(
        n_a,
        n_b,
        type="joins_with",
        weight=1.0,
        src_col="id",
        tgt_col="a_id",
        overlap_pct=100.0,
    )

    hops = find_join_path(G, "t", "a", "b")
    assert len(hops) == 1
    assert hops[0]["from_col"] == "id"
    assert hops[0]["to_col"] == "a_id"
    assert format_join_sql(hops) == "JOIN b ON a.id = b.a_id"


def test_disconnected_graph_returns_empty():
    G = nx.DiGraph()
    G.add_node("s:table:a", name="a")
    G.add_node("s:table:b", name="b")
    assert find_join_path(G, "s", "a", "b") == []


# --- DB Integration Tests ---


@pytest.mark.db
def test_olist_kg_db_persistence():
    engine = get_admin_engine()
    with engine.connect() as conn:
        n_cnt = conn.execute(
            text("SELECT count(*) FROM meta.kg_nodes WHERE source_id = 'olist'")
        ).scalar()
        e_cnt = conn.execute(
            text("SELECT count(*) FROM meta.kg_edges WHERE source_id = 'olist'")
        ).scalar()
        assert n_cnt == 126
        assert e_cnt == 150


@pytest.mark.db
def test_bird_california_schools_kg_db():
    engine = get_admin_engine()
    with engine.connect() as conn:
        n_cnt = conn.execute(
            text(
                "SELECT count(*) FROM meta.kg_nodes WHERE source_id = 'bird:california_schools'"
            )
        ).scalar()
        e_cnt = conn.execute(
            text(
                "SELECT count(*) FROM meta.kg_edges WHERE source_id = 'bird:california_schools'"
            )
        ).scalar()
        assert n_cnt == 185
        assert e_cnt == 188


@pytest.mark.db
def test_multihop_resolution_live():
    engine = get_admin_engine()
    G_olist = load_graph(engine, "olist")
    assert (
        len(find_join_path(G_olist, "olist", "customer.customers", "catalog.products"))
        == 3
    )

    G_bird = load_graph(engine, "bird:california_schools")
    assert (
        len(
            find_join_path(
                G_bird,
                "bird:california_schools",
                "bird_california_schools.satscores",
                "bird_california_schools.frpm",
            )
        )
        == 2
    )
