# src/text2sql/agents/router.py
"""Intent router agent: classifies incoming user questions into discrete operational tracks."""

from typing import Any, Literal
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from src.common.llm import get_chat_model
from src.common.logging import get_logger
from src.text2sql.agents.state import AgentState, IntentType

logger = get_logger("text2sql.agents.router")

ROUTER_SYSTEM_PROMPT = """You are an intent classification specialist for TrustSQL, an enterprise analytics system.
Classify the user's inquiry into exactly ONE of the following 4 categories:

1. 'data_question': Inquiries requesting metrics, data records, aggregations, trends, or lists from operational tables.
   Examples: "Top 10 customers by spend", "Average freight value in SP", "How many schools are charter schools?"

2. 'dq_question': Inquiries specifically questioning data quality, rule scan results, null percentages, data validity, completeness, anomalies, or freshness.
   Examples: "Is order_delivered_customer_date reliable?", "Are there nulls in products?", "Show failing DQ rules".

3. 'metadata_question': Inquiries asking about business definitions, metric calculations, schema structure, column roles, or what data exists.
   Examples: "What is Gross Revenue?", "How is Delivery Delay Days defined?", "List all tables in the customer domain".

4. 'out_of_scope': Generic chitchat, coding requests, general knowledge questions, or unrelated inquiries outside enterprise business database analysis.
   Examples: "Write Python code for quicksort", "Who won the 1994 World Cup?", "Hello, who are you?"

Output your classification strictly adhering to the schema."""


class RouterOutput(BaseModel):
    """Structured output for user question intent classification."""

    intent: Literal[
        "data_question", "dq_question", "metadata_question", "out_of_scope"
    ] = Field(description="The primary intent category")
    reasoning: str = Field(
        description="One-sentence justification for the classification"
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0"
    )


def build_router_prompt() -> ChatPromptTemplate:
    """Builds the prompt template for intent classification."""
    return ChatPromptTemplate.from_messages(
        [("system", ROUTER_SYSTEM_PROMPT), ("human", "User question: {question}")]
    )


def router_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: classifies user intent and populates state['intent']."""
    question = state.get("rewritten_question") or state.get("question", "")
    logger.info("Routing query: %s", question[:80])

    model = get_chat_model(temperature=0.0)
    structured_model = model.with_structured_output(RouterOutput)
    prompt = build_router_prompt()
    chain = prompt | structured_model

    try:
        result: RouterOutput = chain.invoke({"question": question})
        if result and result.intent in (
            "data_question",
            "dq_question",
            "metadata_question",
            "out_of_scope",
        ):
            logger.info(
                "Intent resolved: %s (confidence: %.2f)",
                result.intent,
                result.confidence,
            )
            return {"intent": result.intent}
    except Exception as exc:
        logger.warning(
            "Router structured classification failed: %s; falling back to 'data_question'",
            exc,
        )

    return {"intent": "data_question"}


if __name__ == "__main__":
    test_queries = [
        "Which sellers generated the highest revenue in 2017?",
        "Are there any missing or null values in order delivery dates?",
        "What is the exact business definition and formula for Net Item Revenue?",
        "Can you write a Python script to scrape a website?",
    ]
    print("\n--- Testing Intent Router Node ---")
    for q in test_queries:
        out = router_node({"question": q, "chat_history": []})  # type: ignore
        print(f"Query:  {q}")
        print(f"Intent: {out['intent']}\n")
