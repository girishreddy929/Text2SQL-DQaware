"""tests/test_block10.py: Unit and integration tests for Business Ontology."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from src.common.db import get_admin_engine
from src.metadata.ontology_loader import load_ontology_file
from src.metadata.ontology_models import OntologyFile, OntologyTerm, make_term_id, slug


# --- Unit Tests (No DB) ---


def test_slug_generation():
    assert slug("Gross Revenue") == "gross_revenue"
    assert slug("Percent (%) Eligible Free (K-12)") == "percent_eligible_free_k_12"


def test_term_id_deterministic():
    tid = make_term_id("olist", "metric", "Gross Revenue")
    assert tid == "olist:metric:gross_revenue"


def test_ontology_term_validation():
    t = OntologyTerm(
        source_id="olist",
        term_name="Net Sales",
        term_type="metric",
        definition="Item price sum",
        sql_expression="SUM(price)",
        base_table="sales.order_items",
    )
    assert t.term_id == "olist:metric:net_sales"
    assert t.status == "draft"


def test_ontology_file_source_id_propagation():
    raw = {
        "source_id": "test_src",
        "terms": [
            {
                "term_name": "Test Metric",
                "term_type": "metric",
                "definition": "A test metric",
                "sql_expression": "COUNT(*)",
                "base_table": "test.table",
            }
        ],
    }
    f = OntologyFile(**raw)
    assert f.terms[0].source_id == "test_src"
    assert f.terms[0].term_id == "test_src:metric:test_metric"


# --- DB Integration Tests ---


@pytest.mark.db
def test_olist_ontology_terms_in_db():
    engine = get_admin_engine()
    with engine.connect() as conn:
        cnt = conn.execute(
            text("SELECT count(*) FROM meta.ontology_terms WHERE source_id = 'olist'")
        ).scalar()
        assert cnt == 7


@pytest.mark.db
def test_bird_ontology_terms_in_db():
    engine = get_admin_engine()
    with engine.connect() as conn:
        cnt = conn.execute(
            text(
                "SELECT count(*) FROM meta.ontology_terms WHERE source_id = 'bird:california_schools'"
            )
        ).scalar()
        assert cnt == 5


@pytest.mark.db
def test_ontology_kg_projection_nodes_and_edges():
    engine = get_admin_engine()
    with engine.connect() as conn:
        # Olist: 7 terms -> 7 nodes, 7 edges
        o_nodes = conn.execute(
            text(
                "SELECT count(*) FROM meta.kg_nodes WHERE source_id = 'olist' AND node_type IN ('metric', 'business_term')"
            )
        ).scalar()
        o_edges = conn.execute(
            text(
                "SELECT count(*) FROM meta.kg_edges WHERE source_id = 'olist' AND edge_type = 'measures'"
            )
        ).scalar()
        assert o_nodes == 7
        assert o_edges == 7

        # BIRD: 5 terms -> 5 nodes, 5 edges
        b_nodes = conn.execute(
            text(
                "SELECT count(*) FROM meta.kg_nodes WHERE source_id = 'bird:california_schools' AND node_type IN ('metric', 'business_term')"
            )
        ).scalar()
        b_edges = conn.execute(
            text(
                "SELECT count(*) FROM meta.kg_edges WHERE source_id = 'bird:california_schools' AND edge_type = 'measures'"
            )
        ).scalar()
        assert b_nodes == 5
        assert b_edges == 5


@pytest.mark.db
def test_independent_yaml_db_cross_check():
    """Verify YAML source count matches DB term count."""
    olist_yaml = load_ontology_file("olist")
    bird_yaml = load_ontology_file("bird:california_schools")

    engine = get_admin_engine()
    with engine.connect() as conn:
        db_olist = conn.execute(
            text("SELECT count(*) FROM meta.ontology_terms WHERE source_id = 'olist'")
        ).scalar()
        db_bird = conn.execute(
            text(
                "SELECT count(*) FROM meta.ontology_terms WHERE source_id = 'bird:california_schools'"
            )
        ).scalar()
        assert len(olist_yaml) == db_olist
        assert len(bird_yaml) == db_bird
