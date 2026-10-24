"""Tests for Block 13: LangGraph Core Multi-Agent Graph, State, and Routing."""

import pytest
from src.text2sql.agents.executor import sql_executor_node
from src.text2sql.agents.graph import (
    build_core_graph,
    route_after_execution,
    route_after_validation,
)
from src.text2sql.agents.state import create_initial_state
from src.text2sql.agents.validator_node import sql_validator_node


def test_initial_state_defaults():
    st = create_initial_state("How many orders exist?", source_id="olist")
    assert st["question"] == "How many orders exist?"
    assert st["source_id"] == "olist"
    assert st["retry_count"] == 0
    assert st["max_retries"] == 3
    assert st["is_valid_sql"] is False
    assert st["execution_result"] is None


def test_validator_node_safe_select():
    st = create_initial_state("test")
    st["generated_sql"] = "SELECT * FROM sales.orders"
    res = sql_validator_node(st)
    assert res["is_valid_sql"] is True
    assert "LIMIT 100" in res["generated_sql"]
    assert res["validation_errors"] == []


def test_validator_node_rejects_internal_schemas():
    st = create_initial_state("test")
    st["generated_sql"] = "SELECT * FROM meta.tables"
    res = sql_validator_node(st)
    assert res["is_valid_sql"] is False
    assert "internal schema" in res["validation_errors"][0]


def test_validator_node_handles_none_or_syntax_error():
    st = create_initial_state("test")
    st["generated_sql"] = None
    assert sql_validator_node(st)["is_valid_sql"] is False

    st["generated_sql"] = "SELECT FROM WHERE"
    assert sql_validator_node(st)["is_valid_sql"] is False


def test_routing_logic():
    st = create_initial_state("test", max_retries=3)

    # Validation routing
    st["is_valid_sql"] = True
    assert route_after_validation(st) == "executor"

    st["is_valid_sql"] = False
    st["retry_count"] = 1
    assert route_after_validation(st) == "corrector"

    st["retry_count"] = 3
    assert route_after_validation(st) == "end"

    # Execution routing
    st["error_message"] = None
    assert route_after_execution(st) == "end"

    st["error_message"] = "syntax error"
    st["retry_count"] = 2
    assert route_after_execution(st) == "corrector"

    st["retry_count"] = 3
    assert route_after_execution(st) == "end"


def test_graph_structure_compiles():
    graph = build_core_graph()
    assert graph is not None
    assert "generator" in graph.nodes
    assert "validator" in graph.nodes
    assert "executor" in graph.nodes
    assert "corrector" in graph.nodes


@pytest.mark.db
def test_executor_node_live_query():
    st = create_initial_state("test")
    st["is_valid_sql"] = True
    st["generated_sql"] = "SELECT count(*) FROM sales.orders"
    res = sql_executor_node(st)
    assert res["error_message"] is None
    assert res["row_count"] == 1
    assert res["execution_result"] == [(99441,)]


@pytest.mark.db
def test_executor_node_catches_runtime_error():
    st = create_initial_state("test")
    st["is_valid_sql"] = True
    st["generated_sql"] = "SELECT missing_col FROM sales.orders"
    res = sql_executor_node(st)
    assert res["error_message"] is not None
    assert "does not exist" in res["error_message"]
    assert res["execution_result"] is None
