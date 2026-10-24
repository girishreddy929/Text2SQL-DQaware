"""Agent state definitions for TrustSQL LangGraph multi-agent architecture."""

from __future__ import annotations
from typing import Any, Literal, TypedDict


IntentType = Literal[
    "data_question",
    "dq_question",
    "metadata_question",
    "out_of_scope",
]


class AgentState(TypedDict, total=False):
    # User Inputs & Routing
    question: str
    rewritten_question: str | None
    chat_history: list[dict[str, str]]
    intent: IntentType
    source_id: str
    evidence: str | None

    # Cache & Clarification
    cache_hit: bool
    needs_clarification: bool
    clarification_question: str | None

    # Schema & Metadata Context
    resolved_terms: list[dict[str, Any]]
    selected_domains: list[str]
    selected_tables: list[str]
    selected_columns: list[str]
    join_path: list[dict[str, Any]]

    # SQL Generation, Validation, & Correction Loop
    generated_sql: str | None
    reasoning: str | None
    validation_errors: list[str]
    is_valid_sql: bool
    retry_count: int
    max_retries: int

    # Execution & Results
    execution_result: list[tuple[Any, ...]] | None
    column_names: list[str] | None
    error_message: str | None
    row_count: int

    # DQ & Final Synthesis
    dq_warnings: list[str]
    final_answer: str | None
    chart_suggestion: dict[str, Any] | None


def create_initial_state(
    question: str,
    source_id: str = "olist",
    evidence: str | None = None,
    max_retries: int = 3,
) -> AgentState:
    """Create a clean initial state for graph execution."""
    return {
        "question": question,
        "rewritten_question": None,
        "chat_history": [],
        "intent": "data_question",
        "source_id": source_id,
        "evidence": evidence,
        "cache_hit": False,
        "needs_clarification": False,
        "clarification_question": None,
        "resolved_terms": [],
        "selected_domains": [],
        "selected_tables": [],
        "selected_columns": [],
        "join_path": [],
        "generated_sql": None,
        "reasoning": None,
        "validation_errors": [],
        "is_valid_sql": False,
        "retry_count": 0,
        "max_retries": max_retries,
        "execution_result": None,
        "column_names": None,
        "error_message": None,
        "row_count": 0,
        "dq_warnings": [],
        "final_answer": None,
        "chart_suggestion": None,
    }
