# src/text2sql/agents/ontology_resolver.py
"""Ontology resolver agent: matches business terms/metrics and injects approved SQL formulas."""

from pathlib import Path
from typing import Any
import yaml

from src.common.logging import get_logger
from src.text2sql.agents.state import AgentState

logger = get_logger("text2sql.agents.ontology_resolver")
ONTOLOGY_DIR = Path("config/ontology")


def load_ontology_terms(source_id: str) -> list[dict[str, Any]]:
    """Loads approved terms for a given source from YAML config."""
    clean_id = source_id.replace("bird:", "bird_")
    yaml_file = ONTOLOGY_DIR / f"{clean_id}.yaml"
    if not yaml_file.exists():
        return []

    try:
        with open(yaml_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return [t for t in data.get("terms", []) if t.get("status") == "approved"]
    except Exception as exc:
        logger.warning("Failed to load ontology for %s: %s", source_id, exc)
        return []


def match_terms(question: str, terms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Identifies mentioned ontology terms by name or synonym substring matching."""
    q_lower = question.lower()
    resolved: list[dict[str, Any]] = []
    seen_names = set()

    for term in terms:
        name = term.get("term_name", "")
        synonyms = term.get("synonyms", [])
        candidates = [name.lower()] + [s.lower() for s in synonyms]

        # Match if the full candidate phrase appears in the user query
        if any(c in q_lower for c in candidates if len(c) > 2):
            if name not in seen_names:
                # FIX: Append as a dictionary to a list, including the term_name
                resolved.append(
                    {
                        "term_name": name,
                        "term_type": term.get("term_type"),
                        "definition": term.get("definition"),
                        "sql_expression": term.get("sql_expression"),
                        "base_table": term.get("base_table"),
                        "mapped_columns": term.get("mapped_columns", []),
                    }
                )
                seen_names.add(name)

    return resolved


def ontology_resolver_node(state: AgentState) -> dict[str, Any]:
    """LangGraph node: resolves business terms and populates state['resolved_terms']."""
    question = state.get("rewritten_question") or state.get("question", "")
    source_id = state.get("source_id", "olist")
    intent = state.get("intent", "data_question")

    if intent not in ("data_question", "metadata_question"):
        return {"resolved_terms": []}

    terms = load_ontology_terms(source_id)
    if not terms:
        return {"resolved_terms": []}

    resolved = match_terms(question, terms)
    if resolved:
        logger.info(
            "Resolved %d ontology term(s) for source '%s': %s",
            len(resolved),
            source_id,
            [t["term_name"] for t in resolved],
        )

    return {"resolved_terms": resolved}


if __name__ == "__main__":
    print("\n--- Testing Ontology Resolver Node ---")
    test_state: AgentState = {
        "question": "Show total Gross Revenue and Delivery Delay Days for late orders.",
        "source_id": "olist",
        "intent": "data_question",
    }  # type: ignore

    out = ontology_resolver_node(test_state)
    for details in out["resolved_terms"]:
        print(f"Term:  {details['term_name']}")
        print(f"Table: {details['base_table']}")
        print(f"SQL:   {details['sql_expression']}\n")
