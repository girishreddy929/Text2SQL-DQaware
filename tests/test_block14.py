# tests/test_block14.py
"""Unit and integration tests for Block 14: Intent Router, Rewriter, Clarifier, Ontology, and DQ Advisor."""

import pytest
from src.text2sql.agents.state import AgentState, create_initial_state
from src.text2sql.agents.rewriter import rewriter_node
from src.text2sql.agents.clarifier import clarifier_node
from src.text2sql.agents.ontology_resolver import (
    load_ontology_terms,
    match_terms,
    ontology_resolver_node,
)
from src.text2sql.agents.dq_advisor import (
    format_rule_advisory,
    dq_advisor_node,
    extract_table_names,
)
from src.text2sql.agents.specialists import refusal_node, REFUSAL_MESSAGE
from src.text2sql.agents.graph import (
    build_agentic_graph,
    route_intent,
    route_clarification,
    route_after_validation,
    route_after_execution,
)


def test_rewriter_fast_path():
    """Ensures questions without chat history are returned immediately without LLM invocation."""
    state = create_initial_state(question="Show all orders from SP", source_id="olist")
    out = rewriter_node(state)
    assert out["rewritten_question"] == "Show all orders from SP"


def test_clarifier_skips_non_data():
    """Non-data intents (chitchat, metadata, DQ questions) should never trigger SQL clarification."""
    state: AgentState = {
        "question": "Show me everything",
        "intent": "metadata_question",
    }  # type: ignore
    out = clarifier_node(state)
    assert out["needs_clarification"] is False
    assert out["clarification_question"] is None


def test_ontology_matching():
    """Matches registered Olist metrics by exact phrase or synonym."""
    terms = load_ontology_terms("olist")
    assert len(terms) >= 7
    matched = match_terms("What was our Gross Revenue last month?", terms)
    assert "Gross Revenue" in matched
    assert matched["Gross Revenue"]["base_table"] == "sales.order_payments"
    assert "sum(payment_value)" in matched["Gross Revenue"]["sql_expression"].lower()


def test_format_rule_advisory_dynamic():
    """Verifies dimension-driven executive formatting without hardcoded rule IDs."""
    adv_time = format_rule_advisory(
        "orders", ["order_purchase_timestamp"], "TIMELINESS", "ROW_CONDITION", 0.0
    )
    assert "Historical data window check" in adv_time
    assert "Freshness" in adv_time

    adv_comp = format_rule_advisory(
        "products", ["product_category_name"], "COMPLETENESS", "NON_NULL", 98.15
    )
    assert "Completeness threshold not met" in adv_comp


def test_extract_table_names():
    """Extracts both explicit tables and table mentions from generated SQL."""
    state: AgentState = {
        "selected_tables": ["sales.orders"],
        "generated_sql": "SELECT * FROM catalog.products JOIN sales.order_items USING (product_id)",
    }  # type: ignore
    tables = extract_table_names(state)
    assert "orders" in tables
    assert "products" in tables
    assert "order_items" in tables


def test_refusal_node():
    """Refusal node returns standardized corporate assistance refusal."""
    out = refusal_node({"question": "Write a python game"})  # type: ignore
    assert out["final_answer"] == REFUSAL_MESSAGE


def test_graph_routing_logic():
    """Tests all conditional branching functions across the workflow."""
    assert route_intent({"intent": "out_of_scope"}) == "out_of_scope"  # type: ignore
    assert route_intent({"intent": "data_question"}) == "data_question"  # type: ignore

    assert (
        route_clarification({"needs_clarification": True}) == "clarification_responder"
    )  # type: ignore
    assert route_clarification({"needs_clarification": False}) == "ontology_resolver"  # type: ignore

    # Validation routing
    assert route_after_validation({"is_valid_sql": True}) == "executor"  # type: ignore
    assert (
        route_after_validation(
            {"is_valid_sql": False, "retry_count": 1, "max_retries": 3}
        )
        == "corrector"
    )  # type: ignore
    assert (
        route_after_validation(
            {"is_valid_sql": False, "retry_count": 3, "max_retries": 3}
        )
        == "end"
    )  # type: ignore

    # Execution routing
    assert (
        route_after_execution(
            {"execution_result": [{"count": 10}], "error_message": None}
        )
        == "dq_advisor"
    )  # type: ignore
    assert (
        route_after_execution(
            {
                "execution_result": None,
                "error_message": "DB error",
                "retry_count": 1,
                "max_retries": 3,
            }
        )
        == "corrector"
    )  # type: ignore


def test_graph_compilation():
    """Verifies that the compiled LangGraph builds without cyclic or syntax errors."""
    app = build_agentic_graph()
    assert app is not None


@pytest.mark.db
def test_dq_advisor_live_db():
    """Tests live DB execution of DQ Advisor as t2s_reader against Olist tables."""
    state: AgentState = {
        "source_id": "olist",
        "selected_tables": ["orders", "products"],
        "generated_sql": "SELECT order_id FROM sales.orders",
    }  # type: ignore
    out = dq_advisor_node(state)
    assert "dq_warnings" in out
    assert len(out["dq_warnings"]) > 0
    assert any("Orders" in w or "Products" in w for w in out["dq_warnings"])
