"""tests/test_block11.py: Unit and DB integration tests for Vector Search."""

from __future__ import annotations

import math
import pytest
from sqlalchemy import text
from src.adapters.vectordb.base import VectorItem
from src.adapters.vectordb.pgvector import PostgresVectorStore
from src.common.db import get_admin_engine
from src.metadata.indexer_prep import (
    format_column_payload,
    format_ontology_payload,
    format_table_payload,
    truncate_and_normalize,
)


# --- Unit Tests (No DB) ---


def test_truncate_and_normalize():
    raw = [1.0] * 3072
    vec_768 = truncate_and_normalize(raw, 768)
    assert len(vec_768) == 768
    norm = math.sqrt(sum(x * x for x in vec_768))
    assert abs(norm - 1.0) < 1e-4


def test_format_payloads():
    t_payload = format_table_payload(
        "test", {"schema_name": "s", "table_name": "t", "description": "desc"}, ["c1"]
    )
    assert t_payload.entity_type == "table"
    assert "Columns: c1" in t_payload.text

    c_payload = format_column_payload(
        "test",
        {
            "schema_name": "s",
            "table_name": "t",
            "column_name": "c1",
            "data_type": "int",
        },
    )
    assert c_payload.entity_type == "column"
    assert "Type: int" in c_payload.text

    o_payload = format_ontology_payload(
        "test",
        {
            "term_type": "metric",
            "term_name": "Rev",
            "base_table": "s.t",
            "definition": "d",
            "sql_expression": "SUM(x)",
        },
    )
    assert o_payload.entity_type == "metric"
    assert "Formula: SUM(x)" in o_payload.text


# --- DB Integration Tests ---


@pytest.mark.db
def test_pgvector_add_and_search_synthetic():
    store = PostgresVectorStore(get_admin_engine())
    unit_vec = [1.0 / math.sqrt(768)] * 768
    item = VectorItem(
        id="test:synthetic:item",
        source_id="test_suite",
        entity_type="metric",
        entity_name="Test Metric",
        content="Synthetic test content",
        embedding=unit_vec,
    )
    store.add_items([item])
    results = store.similarity_search(
        query_vector=unit_vec, k=1, source_id="test_suite"
    )
    assert len(results) == 1
    assert results[0].id == "test:synthetic:item"
    assert abs(results[0].score - 1.0) < 1e-3
    store.delete_by_source("test_suite")


@pytest.mark.db
def test_indexed_schema_counts():
    engine = get_admin_engine()
    with engine.connect() as conn:
        # Olist: 11 tables + 70 columns + 7 ontology terms = 88
        o_cnt = conn.execute(
            text(
                "SELECT count(*) FROM meta.schema_embeddings WHERE source_id = 'olist'"
            )
        ).scalar()
        assert o_cnt == 88

        # BIRD california_schools: 3 tables + 89 columns + 5 ontology terms = 97
        b_cnt = conn.execute(
            text(
                "SELECT count(*) FROM meta.schema_embeddings WHERE source_id = 'bird:california_schools'"
            )
        ).scalar()
        assert b_cnt == 97


@pytest.mark.db
def test_filter_by_entity_type():
    store = PostgresVectorStore(get_admin_engine())
    dummy_vec = [0.0] * 768
    dummy_vec[0] = 1.0
    results = store.similarity_search(
        query_vector=dummy_vec, k=5, source_id="olist", entity_types=["table"]
    )
    assert len(results) > 0
    assert all(r.entity_type == "table" for r in results)
