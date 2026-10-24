# src/text2sql/agents/specialists.py
"""Specialist agents: dedicated handling for DQ queries, metadata inquiries, and out-of-scope refusals."""

from typing import Any
from sqlalchemy import text
from langchain_core.prompts import ChatPromptTemplate

from src.common.db import get_reader_engine
from src.common.llm import get_chat_model, response_text
from src.common.logging import get_logger
from src.text2sql.agents.state import AgentState
from src.text2sql.agents.ontology_resolver import load_ontology_terms

logger = get_logger("text2sql.agents.specialists")

REFUSAL_MESSAGE = (
    "I am TrustSQL, an enterprise data assistant. I can only answer questions related to "
    "enterprise database records, data quality scan results, and business metric definitions. "
    "Please ask a business data or analytics question."
)


def refusal_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: politely refuses out-of-scope inquiries."""
    logger.info("Routing to refusal node.")
    return {"final_answer": REFUSAL_MESSAGE}


def dq_agent_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: answers data quality inquiries using latest scan results."""
    question = state.get("rewritten_question") or state.get("question", "")
    source_id = state.get("source_id", "olist")
    logger.info("DQ Specialist handling question for source '%s'", source_id)

    reader = get_reader_engine()
    summary_lines = []
    try:
        with reader.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT rule_id, table_name, rule_type, pass_pct, status
                    FROM dq.latest_results
                    WHERE source_id = :source_id
                    ORDER BY status DESC, pass_pct ASC
                    LIMIT 15;
                """),
                {"source_id": source_id},
            ).fetchall()
            for r in rows:
                summary_lines.append(
                    f"- Rule {r.rule_id} on {r.table_name} ({r.rule_type}): {r.status} ({float(r.pass_pct):.1f}% pass)"
                )
    except Exception as exc:
        logger.warning("Failed to fetch DQ summary: %s", exc)

    dq_context = "\n".join(summary_lines) or "No scan results available."

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a Data Quality Specialist. Answer the user's question clearly based ONLY on the provided scan results.\n\nScan Results:\n{context}",
            ),
            ("human", "{question}"),
        ]
    )
    model = get_chat_model(temperature=0.0)
    response = (prompt | model).invoke({"context": dq_context, "question": question})
    return {"final_answer": response_text(response)}


def metadata_agent_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: answers metadata and business concept questions using the ontology."""
    question = state.get("rewritten_question") or state.get("question", "")
    source_id = state.get("source_id", "olist")
    logger.info("Metadata Specialist handling question for source '%s'", source_id)

    terms = load_ontology_terms(source_id)
    terms_text = (
        "\n".join(
            [
                f"- {t['term_name']} ({t.get('term_type', 'metric')}): {t.get('definition', '')} [Formula: {t.get('sql_expression', 'N/A')} on {t.get('base_table', 'N/A')}]"
                for t in terms
            ]
        )
        or "No ontology terms registered."
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a Business Ontology and Data Governance Specialist. Answer the user's question accurately based on the approved terms.\n\nApproved Terms:\n{terms}",
            ),
            ("human", "{question}"),
        ]
    )
    model = get_chat_model(temperature=0.0)
    response = (prompt | model).invoke({"terms": terms_text, "question": question})
    return {"final_answer": response_text(response)}


if __name__ == "__main__":
    print("\n--- Testing Specialist Nodes ---")
    print("\n1. Refusal Node:")
    print(refusal_node({"question": "Write a song"}))  # type: ignore

    print("\n2. DQ Specialist Node:")
    dq_out = dq_agent_node(
        {
            "question": "Are there any failing data quality rules in Olist?",
            "source_id": "olist",
        }
    )  # type: ignore
    print(dq_out["final_answer"])

    print("\n3. Metadata Specialist Node:")
    meta_out = metadata_agent_node(
        {"question": "How is Gross Revenue defined?", "source_id": "olist"}
    )  # type: ignore
    print(meta_out["final_answer"])
