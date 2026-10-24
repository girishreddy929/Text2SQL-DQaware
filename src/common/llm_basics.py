"""Run:  python -m src.common.llm_basics
Shows: raw call, prompt template, chain (prompt | model | parser), batch."""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

from src.common.llm import get_chat_model, response_text


def main() -> None:
    model = get_chat_model()

    print("1) RAW CALL")
    msg = model.invoke("Reply with exactly one word: hello")
    print("   type    :", type(msg).__name__)
    print("   content :", type(msg.content).__name__, "->", repr(msg.content)[:80])
    print("   text    :", response_text(msg))
    print("   usage   :", msg.usage_metadata)

    print("\n2) PROMPT TEMPLATE")
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "You are a {role}. Answer in at most {n} words."),
            ("human", "{question}"),
        ]
    )
    filled = prompt.invoke(
        {"role": "data analyst", "n": 12, "question": "What is a primary key?"}
    )
    for m in filled.messages:
        print(f"   [{m.type}] {m.content}")

    print("\n3) CHAIN = prompt | model | parser")
    chain = prompt | model | RunnableLambda(response_text)
    print(
        "  ",
        chain.invoke({"role": "SQL tutor", "n": 15, "question": "What is a JOIN?"}),
    )

    print("\n4) BATCH (3 questions, max 2 at once)")
    inputs = [
        {"role": "analyst", "n": 8, "question": q}
        for q in ("What is NULL?", "What is GROUP BY?", "What is an index?")
    ]
    for out in chain.batch(inputs, config={"max_concurrency": 2}):
        print("  -", out)

    print("\n5) BRACES IN TEMPLATES")
    t = ChatPromptTemplate.from_messages(
        [("human", 'Return JSON like {{"sql": "..."}} for: {q}')]
    )
    print("  ", t.invoke({"q": "count orders"}).messages[0].content)


if __name__ == "__main__":
    main()
