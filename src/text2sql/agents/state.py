# src/text2sql/agents/state.py
from typing import TypedDict, Literal, Any

IntentType = Literal[
    "data_question", "dq_question", "metadata_question", "out_of_scope", "unknown"
]


class AgentState(TypedDict, total=False):
    # Input & Context
    question: str
    rewritten_question: str
    chat_history: list[dict]
    source_id: str
    evidence: str
    eval_mode: bool  # <--- ADDED THIS KEY

    # Routing & Clarification
    intent: IntentType
    needs_clarification: bool
    clarification_question: str

    # Cache
    cache_hit: bool

    # Schema & Ontology
    resolved_terms: list[dict]
    selected_domains: list[str]
    selected_tables: list[str]
    selected_columns: list[str]
    join_path: str

    # Generation & Validation
    generated_sql: str
    reasoning: str
    validation_errors: str
    is_valid_sql: bool

    # Execution & Retries
    retry_count: int
    max_retries: int
    execution_result: list[dict]
    column_names: list[str]
    error_message: str
    row_count: int

    # Final Output
    dq_warnings: list[str]
    final_answer: str
    chart_suggestion: str


def create_initial_state() -> AgentState:
    return {
        "question": "",
        "rewritten_question": "",
        "chat_history": [],
        "source_id": "olist",
        "evidence": "",
        "eval_mode": False,
        "intent": "unknown",
        "needs_clarification": False,
        "clarification_question": "",
        "cache_hit": False,
        "resolved_terms": [],
        "selected_domains": [],
        "selected_tables": [],
        "selected_columns": [],
        "join_path": "",
        "generated_sql": "",
        "reasoning": "",
        "validation_errors": "",
        "is_valid_sql": False,
        "retry_count": 0,
        "max_retries": 3,
        "execution_result": [],
        "column_names": [],
        "error_message": "",
        "row_count": 0,
        "dq_warnings": [],
        "final_answer": "",
        "chart_suggestion": "",
    }
