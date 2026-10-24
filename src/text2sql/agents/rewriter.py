# src/text2sql/agents/rewriter.py
"""Query rewriter agent: resolves conversational context and pronouns into standalone queries."""

from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.common.llm import get_chat_model
from src.common.logging import get_logger
from src.text2sql.agents.state import AgentState

logger = get_logger("text2sql.agents.rewriter")

REWRITER_SYSTEM_PROMPT = """You are a conversational query rewriting specialist.
Given the previous chat conversation and the latest user question:
1. If the question refers to earlier turns (pronouns like "they", "those", "that", or ellipsis like "what about RJ?"):
   rewrite it into a completely standalone, self-contained question preserving all original constraints.
2. If the question is already fully self-contained or requires no earlier context:
   return it verbatim without altering the wording.
3. Do NOT attempt to answer or generate SQL. Only output the rewritten question."""


class RewriterOutput(BaseModel):
    """Structured output for query disambiguation."""

    rewritten_question: str = Field(
        description="Self-contained question with all conversational references resolved"
    )
    was_rewritten: bool = Field(
        description="Whether the original question needed modification"
    )


def build_rewriter_prompt() -> ChatPromptTemplate:
    """Builds the prompt template for query rewriting."""
    return ChatPromptTemplate.from_messages(
        [
            ("system", REWRITER_SYSTEM_PROMPT),
            (
                "human",
                "Conversation History:\n{history}\n\nLatest Question:\n{question}",
            ),
        ]
    )


def format_history(chat_history: list[dict[str, str]]) -> str:
    """Formats recent turns into readable dialogue text."""
    if not chat_history:
        return "None"
    lines = []
    for turn in chat_history[-6:]:  # Keep last 3 dialogue pairs
        role = turn.get("role", "user").capitalize()
        content = turn.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def rewriter_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: rewrites conversational queries into self-contained questions."""
    question = state.get("question", "").strip()
    chat_history = state.get("chat_history", [])

    # Fast path: if no chat history exists, question is already standalone
    if not chat_history:
        logger.info("No chat history present; keeping original question.")
        return {"rewritten_question": question}

    logger.info("Rewriting question with %d history turns...", len(chat_history))
    model = get_chat_model(temperature=0.0)
    structured_model = model.with_structured_output(RewriterOutput)
    prompt = build_rewriter_prompt()
    chain = prompt | structured_model

    try:
        history_text = format_history(chat_history)
        result: RewriterOutput = chain.invoke(
            {"history": history_text, "question": question}
        )
        if result and result.rewritten_question:
            logger.info(
                "Rewritten: '%s' -> '%s' (modified=%s)",
                question,
                result.rewritten_question,
                result.was_rewritten,
            )
            return {"rewritten_question": result.rewritten_question}
    except Exception as exc:
        logger.warning("Rewriter failed: %s; falling back to original query", exc)

    return {"rewritten_question": question}


if __name__ == "__main__":
    print("\n--- Testing Query Rewriter Node ---")
    mock_history = [
        {
            "role": "user",
            "content": "Show me total revenue for sellers in Sao Paulo in 2017.",
        },
        {
            "role": "assistant",
            "content": "Total revenue for SP sellers in 2017 was $2,145,000 across 12,400 orders.",
        },
    ]
    test_state: AgentState = {
        "question": "What about in Rio de Janeiro?",
        "chat_history": mock_history,
    }  # type: ignore

    out = rewriter_node(test_state)
    print(f"Original:  {test_state['question']}")
    print(f"Rewritten: {out['rewritten_question']}\n")
