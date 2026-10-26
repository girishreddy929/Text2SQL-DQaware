# src/text2sql/agents/router.py
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from src.common.llm import get_chat_model
from src.common.logging import get_logger
from src.text2sql.agents.state import IntentType

logger = get_logger(__name__)


class RouterOutput(BaseModel):
    intent: IntentType = Field(
        description="The classified intent of the user's question."
    )
    reasoning: str = Field(description="Brief reasoning for the classification.")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0.")


def build_router_prompt() -> ChatPromptTemplate:
    sys_msg = """You are the Chief Routing Agent for an enterprise data assistant.
Your job is to classify the user's question into exactly one of these intents:

1. data_question: The user wants to query actual business data (e.g., "Show me sales", "How many customers?", "What are the distinct order statuses?").
2. dq_question: The user is asking about data quality, nulls, duplicates, or reliability (e.g., "Is the email column clean?", "Can I trust the revenue data?").
3. metadata_question: The user is asking about definitions, ontology, or schema structure (e.g., "What does Gross Revenue mean?", "What tables exist?").
4. out_of_scope: The user is asking something completely unrelated to the database (e.g., "Write a poem", "Who is the president?").

CRITICAL RULE: If the user asks for "distinct values", "unique statuses", or "list the categories", that requires querying the database. It is a data_question, NOT a metadata_question.
"""
    return ChatPromptTemplate.from_messages(
        [("system", sys_msg), ("user", "Question: {question}")]
    )


def router_node(state: dict) -> dict:
    question = state.get("rewritten_question") or state.get("question")
    logger.info(f"Routing query: {question}")

    prompt = build_router_prompt()
    llm = get_chat_model(temperature=0.0).with_structured_output(RouterOutput)
    chain = prompt | llm

    try:
        result = chain.invoke({"question": question})
        if result:
            logger.info(
                f"Intent resolved: {result.intent} (confidence: {result.confidence:.2f})"
            )
            return {"intent": result.intent}
    except Exception as e:
        logger.error(f"Routing failed: {e}")

    # Fallback to data_question if routing fails
    return {"intent": "data_question"}
