# tests/test_block16.py
import pytest
import uuid

from src.app.cache import SemanticCache
from src.text2sql.agents.cache_nodes import cache_lookup_node
from src.text2sql.agents.schema_linker import schema_linker_node
from src.text2sql.agents.domain_selector import domain_selector_node
from src.text2sql.agents.generator import build_targeted_schema_context

# --- BLOCK 15 TESTS (Semantic Cache) ---


@pytest.mark.db
def test_semantic_cache_add_search():
    """Tests adding to and searching the pgvector semantic cache."""
    cache = SemanticCache()
    unique_q = f"Test query {uuid.uuid4()}"

    # Add a dummy query
    cache_id = cache.add(
        "olist", unique_q, "SELECT 1", ["sales.orders"], feedback_score=1
    )
    assert cache_id is not None

    # Search for it
    results = cache.search("olist", unique_q, limit=1)
    assert len(results) > 0
    assert results[0].question == unique_q
    assert results[0].generated_sql == "SELECT 1"


@pytest.mark.db
@pytest.mark.llm
def test_cache_lookup_node_miss():
    """Tests that a completely unknown question results in a cache miss."""
    state = {
        "question": f"Completely random question {uuid.uuid4()}",
        "source_id": "olist",
    }
    res = cache_lookup_node(state)
    assert res.get("cache_hit") is False


# --- BLOCK 16 TESTS (Cross-Domain Schema Linking) ---


@pytest.mark.db
def test_schema_linker_node():
    """Tests that the vector search retrieves relevant tables."""
    state = {
        "question": "Show me orders and payments",
        "source_id": "olist",
        "resolved_terms": [],
    }
    res = schema_linker_node(state)

    assert "selected_tables" in res
    assert isinstance(res["selected_tables"], list)
    # It should find at least one of the relevant tables
    assert any("order" in t or "payment" in t for t in res["selected_tables"])


@pytest.mark.db
def test_domain_selector_node():
    """Tests that the KG correctly finds multi-hop join paths."""
    state = {
        "source_id": "olist",
        "selected_tables": ["customer.customers", "catalog.products"],
    }
    res = domain_selector_node(state)

    assert "join_path" in res
    assert "Known valid join conditions" in res["join_path"]

    # It should automatically discover the intermediate tables needed to bridge the gap
    assert "sales.orders" in res["selected_tables"]
    assert "sales.order_items" in res["selected_tables"]


@pytest.mark.db
def test_build_targeted_schema_context():
    """Tests that the schema context is strictly filtered to selected tables."""
    ctx = build_targeted_schema_context("olist", ["sales.orders"])

    assert "Table: sales.orders" in ctx
    assert "order_id" in ctx
    # It should NOT contain tables that weren't selected
    assert "customer.customers" not in ctx
