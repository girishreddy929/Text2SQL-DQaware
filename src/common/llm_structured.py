"""Run:  python -m src.common.llm_structured
Shows: structured output with Pydantic (SQL generator shape + router shape)."""

from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.common.llm import get_chat_model

SCHEMA = 'sales.orders("order_id" text, "order_status" text, "order_delivered_customer_date" timestamp)'


class SqlAnswer(BaseModel):
    """What the SQL Generator agent will return."""

    sql: str = Field(description="One PostgreSQL SELECT statement")
    reasoning: str = Field(description="One or two sentences explaining the logic")
    tables_used: list[str] = Field(description="schema.table names used by the SQL")


class Route(BaseModel):
    """What the Router agent will return."""

    intent: Literal["data_question", "dq_question", "metadata_question", "out_of_scope"]
    confidence: float = Field(ge=0, le=1)


def main() -> None:
    model = get_chat_model()

    print("1) SQL GENERATOR SHAPE")
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "You write PostgreSQL SELECT queries. Schema: {schema}"),
            ("human", "{question}"),
        ]
    )
    chain = prompt | model.with_structured_output(SqlAnswer)
    out = chain.invoke({"schema": SCHEMA, "question": "How many orders per status?"})
    print("   type       :", type(out).__name__)
    print("   sql        :", out.sql)
    print("   reasoning  :", out.reasoning)
    print("   tables_used:", out.tables_used)

    print("\n2) ROUTER SHAPE (Literal restricts the answer)")
    router = ChatPromptTemplate.from_messages(
        [
            ("system", "Classify the user message into one intent."),
            ("human", "{q}"),
        ]
    ) | model.with_structured_output(Route)
    for q in (
        "Top 5 sellers by revenue?",
        "Which tables have the most null values?",
        "What does the column order_status mean?",
        "Write me a poem about the sea",
    ):
        r = router.invoke({"q": q})
        print(f"   {r.intent:18} {r.confidence:.2f}  <- {q}")


if __name__ == "__main__":
    main()
