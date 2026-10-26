# src/text2sql/agents/graph.py
from langgraph.graph import StateGraph, END, START
from src.common.logging import get_logger

from src.text2sql.agents.state import AgentState
from src.text2sql.agents.router import router_node
from src.text2sql.agents.rewriter import rewriter_node
from src.text2sql.agents.clarifier import clarifier_node
from src.text2sql.agents.cache_nodes import cache_lookup_node
from src.text2sql.agents.ontology_resolver import ontology_resolver_node
from src.text2sql.agents.schema_linker import schema_linker_node
from src.text2sql.agents.domain_selector import domain_selector_node
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

logger = get_logger(__name__)


def clarification_responder(state: dict) -> dict:
    """Returns the clarification question directly to the user."""
    return {
        "final_answer": state.get(
            "clarification_question", "Could you please clarify your request?"
        )
    }


def answer_synthesizer(state: dict) -> dict:
    """Synthesizes the final answer from execution results and DQ warnings."""
    res = state.get("execution_result", [])
    warnings = state.get("dq_warnings", [])

    ans = f"Here are the results for your query:\n{res[:5]}"
    if len(res) > 5:
        ans += f"\n... and {len(res) - 5} more rows."

    if warnings:
        ans += "\n\nData Quality Warnings:\n" + "\n".join(warnings)

    return {"final_answer": ans}


def route_intent(state: dict) -> str:
    intent = state.get("intent")
    if intent == "dq_question":
        return "dq_agent"
    elif intent == "metadata_question":
        return "metadata_agent"
    elif intent == "out_of_scope":
        return "refusal"
    return "rewriter"


def route_clarification(state: dict) -> str:
    if state.get("needs_clarification"):
        return "clarification_responder"
    return "cache_lookup"


def route_after_cache(state: dict) -> str:
    if state.get("cache_hit"):
        logger.info("Routing directly to executor (Cache Hit)")
        return "sql_executor"
    return "ontology_resolver"


def route_after_validation(state: dict) -> str:
    if state.get("is_valid_sql"):
        return "sql_executor"
    if state.get("retry_count", 0) >= state.get("max_retries", 3):
        return "answer_synthesizer"
    return "sql_corrector"


def route_after_execution(state: dict) -> str:
    if state.get("error_message"):
        if state.get("retry_count", 0) >= state.get("max_retries", 3):
            return "answer_synthesizer"
        return "sql_corrector"
    return "dq_advisor"


def build_agentic_graph() -> StateGraph:
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("router", router_node)
    workflow.add_node("rewriter", rewriter_node)
    workflow.add_node("clarifier", clarifier_node)
    workflow.add_node("clarification_responder", clarification_responder)
    workflow.add_node("cache_lookup", cache_lookup_node)
    workflow.add_node("ontology_resolver", ontology_resolver_node)
    workflow.add_node("schema_linker", schema_linker_node)
    workflow.add_node("domain_selector", domain_selector_node)
    workflow.add_node("sql_generator", sql_generator_node)
    workflow.add_node("sql_validator", sql_validator_node)
    workflow.add_node("sql_executor", sql_executor_node)
    workflow.add_node("sql_corrector", sql_corrector_node)
    workflow.add_node("dq_advisor", dq_advisor_node)
    workflow.add_node("answer_synthesizer", answer_synthesizer)
    workflow.add_node("dq_agent", dq_agent_node)
    workflow.add_node("metadata_agent", metadata_agent_node)
    workflow.add_node("refusal", refusal_node)

    # Edges
    workflow.add_edge(START, "router")

    workflow.add_conditional_edges(
        "router",
        route_intent,
        {
            "rewriter": "rewriter",
            "dq_agent": "dq_agent",
            "metadata_agent": "metadata_agent",
            "refusal": "refusal",
        },
    )

    workflow.add_edge("rewriter", "clarifier")

    workflow.add_conditional_edges(
        "clarifier",
        route_clarification,
        {
            "clarification_responder": "clarification_responder",
            "cache_lookup": "cache_lookup",
        },
    )

    workflow.add_conditional_edges(
        "cache_lookup",
        route_after_cache,
        {"sql_executor": "sql_executor", "ontology_resolver": "ontology_resolver"},
    )

    # New Cross-Domain Flow
    workflow.add_edge("ontology_resolver", "schema_linker")
    workflow.add_edge("schema_linker", "domain_selector")
    workflow.add_edge("domain_selector", "sql_generator")

    workflow.add_edge("sql_generator", "sql_validator")

    workflow.add_conditional_edges(
        "sql_validator",
        route_after_validation,
        {
            "sql_executor": "sql_executor",
            "sql_corrector": "sql_corrector",
            "answer_synthesizer": "answer_synthesizer",
        },
    )

    workflow.add_conditional_edges(
        "sql_executor",
        route_after_execution,
        {
            "dq_advisor": "dq_advisor",
            "sql_corrector": "sql_corrector",
            "answer_synthesizer": "answer_synthesizer",
        },
    )

    workflow.add_edge("sql_corrector", "sql_generator")
    workflow.add_edge("dq_advisor", "answer_synthesizer")

    # End edges
    workflow.add_edge("clarification_responder", END)
    workflow.add_edge("answer_synthesizer", END)
    workflow.add_edge("dq_agent", END)
    workflow.add_edge("metadata_agent", END)
    workflow.add_edge("refusal", END)

    return workflow.compile()


# Alias for backward compatibility
build_core_graph = build_agentic_graph


def run_agentic_text2sql(
    question: str,
    source_id: str,
    evidence: str = "",
    chat_history: list = None,
    max_retries: int = 3,
    eval_mode: bool = False,
) -> dict:
    graph = build_agentic_graph()
    initial_state = {
        "question": question,
        "source_id": source_id,
        "evidence": evidence,
        "chat_history": chat_history or [],
        "max_retries": max_retries,
        "eval_mode": eval_mode,
    }
    return graph.invoke(initial_state)


if __name__ == "__main__":
    # Full pipeline test (Cache Miss -> Ontology -> Schema Linker -> Domain Selector -> Generator)
    # We use specific thresholds so the Clarifier lets it pass!
    print("--- Testing Full Cross-Domain Pipeline ---")
    res = run_agentic_text2sql(
        "List the customer ids and the product category names they bought, where the payment value was greater than 1000.",
        "olist",
    )

    print(f"\nSelected Tables: {res.get('selected_tables')}")
    print(f"Join Path:\n{res.get('join_path')}")
    print(f"Generated SQL:\n{res.get('generated_sql')}")
    print(f"Final Answer:\n{res.get('final_answer')}")
