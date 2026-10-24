# src/text2sql/agents/clarifier.py
"""Clarifier agent: detects critical ambiguities requiring user clarification."""

from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.common.llm import get_chat_model
from src.common.logging import get_logger
from src.text2sql.agents.state import AgentState

logger = get_logger("text2sql.agents.clarifier")

CLARIFIER_SYSTEM_PROMPT = """You are an ambiguity detection specialist for an enterprise Text2SQL system.
Analyze the user's inquiry and determine if it requires clarification:

1. Flag as ambiguous (is_ambiguous = true) ONLY if:
   - The query lacks critical constraints to select a table or metric (e.g., "Show me the best items" - rating, revenue, or volume?).
   - Key entities or filters are completely contradictory or indefinable.
2. Do NOT flag as ambiguous (is_ambiguous = false) if:
   - The question can be answered using standard business defaults (e.g., "top customers" -> customer revenue; "late orders" -> order delivery delay).
   - The question is straightforward, specific, or already well-constrained.

Be conservative: do not unnecessarily interrupt users if a sensible default interpretation exists."""


class ClarifierOutput(BaseModel):
    """Structured output for ambiguity assessment."""

    is_ambiguous: bool = Field(
        description="True if clarification is strictly required from the user"
    )
    clarification_question: str | None = Field(
        default=None,
        description="Concise question asking user for the missing criteria, or None if clear",
    )
    reasoning: str = Field(description="Brief rationale for this decision")


def build_clarifier_prompt() -> ChatPromptTemplate:
    """Builds the prompt template for ambiguity detection."""
    return ChatPromptTemplate.from_messages(
        [("system", CLARIFIER_SYSTEM_PROMPT), ("human", "Question: {question}")]
    )


def clarifier_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: evaluates query ambiguity and populates clarification flags."""
    question = state.get("rewritten_question") or state.get("question", "")
    intent = state.get("intent", "data_question")

    # Non-data questions (chitchat, DQ scans, metadata) do not need SQL clarification
    if intent != "data_question":
        return {"needs_clarification": False, "clarification_question": None}

    logger.info("Evaluating ambiguity for: %s", question[:80])
    model = get_chat_model(temperature=0.0)
    structured_model = model.with_structured_output(ClarifierOutput)
    prompt = build_clarifier_prompt()
    chain = prompt | structured_model

    try:
        result: ClarifierOutput = chain.invoke({"question": question})
        if result and result.is_ambiguous and result.clarification_question:
            logger.info("Clarification needed: %s", result.clarification_question)
            return {
                "needs_clarification": True,
                "clarification_question": result.clarification_question,
            }
    except Exception as exc:
        logger.warning(
            "Clarifier evaluation failed: %s; proceeding without interruption", exc
        )

    return {"needs_clarification": False, "clarification_question": None}


if __name__ == "__main__":
    print("\n--- Testing Clarifier Node ---")
    queries = [
        "Show top 10 products by total delivered revenue.",
        "Show me the best products.",
    ]
    for q in queries:
        out = clarifier_node({"question": q, "intent": "data_question"})  # type: ignore
        print(f"Question:  {q}")
        print(f"Ambiguous: {out['needs_clarification']}")
        print(f"Prompt:    {out['clarification_question']}\n")
