# src/text2sql/agents/graph.py
"""Complete LangGraph orchestration for TrustSQL multi-agent Text2SQL pipeline."""

from typing import Any
from langgraph.graph import StateGraph, START, END

from src.common.logging import get_logger
from src.text2sql.agents.state import AgentState, create_initial_state
from src.text2sql.agents.router import router_node
from src.text2sql.agents.rewriter import rewriter_node
from src.text2sql.agents.clarifier import clarifier_node
from src.text2sql.agents.ontology_resolver import ontology_resolver_node
from src.text2sql.agents.generator import sql_generator_node
from src.text2sql.agents.validator_node import sql_validator_node
from src.text2sql.agents.executor import sql_executor_node
from src.text2sql.agents.corrector import sql_corrector_node
from src.text2sql.agents.dq_advisor import dq_advisor_node
from src.text2sql.agents.specialists import (
    refusal_node,
    dq_agent_node,
    metadata_agent_node,
)

logger = get_logger("text2sql.agents.graph")


def clarification_responder(state: AgentState) -> dict[str, Any]:
    """Node: formats clarification question into final answer."""
    return {
        "final_answer": state.get("clarification_question")
        or "Please clarify your inquiry."
    }


def answer_synthesizer(state: AgentState) -> dict[str, Any]:
    """Node: synthesizes data rows, SQL context, and DQ advisories into final response."""
    rows = state.get("execution_result") or []
    count = state.get("row_count", len(rows))
    warnings = state.get("dq_warnings") or []

    parts = [f"Found {count} result(s)."]
    if warnings:
        parts.append(
            "\nData Quality Warnings:\n" + "\n".join(f"- {w}" for w in warnings)
        )
    return {"final_answer": "\n".join(parts)}


def route_intent(state: AgentState) -> str:
    return state.get("intent", "data_question")


def route_clarification(state: AgentState) -> str:
    return (
        "clarification_responder"
        if state.get("needs_clarification")
        else "ontology_resolver"
    )


def route_after_validation(state: AgentState) -> str:
    if state.get("is_valid_sql", False):
        return "executor"
    return (
        "corrector"
        if state.get("retry_count", 0) < state.get("max_retries", 3)
        else "end"
    )


def route_after_execution(state: AgentState) -> str:
    if state.get("execution_result") is not None and not state.get("error_message"):
        return "dq_advisor"
    return (
        "corrector"
        if state.get("retry_count", 0) < state.get("max_retries", 3)
        else "end"
    )


def build_agentic_graph() -> Any:
    workflow = StateGraph(AgentState)

    workflow.add_node("router", router_node)
    workflow.add_node("refusal", refusal_node)
    workflow.add_node("dq_specialist", dq_agent_node)
    workflow.add_node("metadata_specialist", metadata_agent_node)
    workflow.add_node("rewriter", rewriter_node)
    workflow.add_node("clarifier", clarifier_node)
    workflow.add_node("clarification_responder", clarification_responder)
    workflow.add_node("ontology_resolver", ontology_resolver_node)
    workflow.add_node("generator", sql_generator_node)
    workflow.add_node("validator", sql_validator_node)
    workflow.add_node("executor", sql_executor_node)
    workflow.add_node("corrector", sql_corrector_node)
    workflow.add_node("dq_advisor", dq_advisor_node)
    workflow.add_node("synthesizer", answer_synthesizer)

    workflow.add_edge(START, "router")
    workflow.add_conditional_edges(
        "router",
        route_intent,
        {
            "out_of_scope": "refusal",
            "dq_question": "dq_specialist",
            "metadata_question": "metadata_specialist",
            "data_question": "rewriter",
        },
    )
    workflow.add_edge("refusal", END)
    workflow.add_edge("dq_specialist", END)
    workflow.add_edge("metadata_specialist", END)

    workflow.add_edge("rewriter", "clarifier")
    workflow.add_conditional_edges(
        "clarifier",
        route_clarification,
        {
            "clarification_responder": "clarification_responder",
            "ontology_resolver": "ontology_resolver",
        },
    )
    workflow.add_edge("clarification_responder", END)

    workflow.add_edge("ontology_resolver", "generator")
    workflow.add_edge("generator", "validator")
    workflow.add_conditional_edges(
        "validator",
        route_after_validation,
        {"executor": "executor", "corrector": "corrector", "end": END},
    )
    workflow.add_edge("corrector", "validator")
    workflow.add_conditional_edges(
        "executor",
        route_after_execution,
        {"dq_advisor": "dq_advisor", "corrector": "corrector", "end": END},
    )
    workflow.add_edge("dq_advisor", "synthesizer")
    workflow.add_edge("synthesizer", END)

    return workflow.compile()


# Backward-compatible alias for Block 13 tests
build_core_graph = build_agentic_graph


def run_agentic_text2sql(
    question: str,
    source_id: str = "olist",
    evidence: str | None = None,
    chat_history: list[dict[str, str]] | None = None,
    max_retries: int = 3,
) -> dict[str, Any]:
    graph = build_agentic_graph()
    state = create_initial_state(
        question=question,
        source_id=source_id,
        evidence=evidence,
        max_retries=max_retries,
    )
    if chat_history:
        state["chat_history"] = chat_history
    return graph.invoke(state)
