# src/text2sql/agents/cache_nodes.py
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from src.app.cache import SemanticCache
from src.common.llm import get_chat_model
from src.common.logging import get_logger

logger = get_logger(__name__)


class CacheVerification(BaseModel):
    is_match: bool = Field(
        description="True if the questions ask for the exact same data, filters, and aggregations."
    )
    reason: str = Field(description="Reason for the decision.")


def cache_lookup_node(state: dict) -> dict:
    """Searches the semantic cache and uses an LLM to verify exact parameter matches."""
    question = state.get("rewritten_question") or state.get("question")
    source_id = state.get("source_id")

    if not question or not source_id:
        return {"cache_hit": False}

    cache = SemanticCache()
    # Find top match with high cosine similarity
    matches = cache.search(source_id, question, limit=1, threshold=0.85)

    if not matches:
        logger.info("Cache MISS: No similar questions found.")
        return {"cache_hit": False}

    best_match = matches[0]
    logger.info(
        f"Cache candidate found (sim: {best_match.similarity:.4f}): '{best_match.question}'"
    )

    # Verify exact match with LLM
    llm = get_chat_model(temperature=0.0).with_structured_output(CacheVerification)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a Semantic Cache Verifier. Your job is to prevent false positive cache hits.",
            ),
            (
                "user",
                """Compare these two questions:
New Question: {new_q}
Cached Question: {cached_q}

Do they ask for the EXACT same data, with the exact same filters, entities, and aggregations?
If one asks for '2022' and the other for '2023', or one asks for 'revenue' and the other for 'profit', they are NOT a match.
Return true ONLY if the SQL for the cached question would perfectly answer the new question.""",
            ),
        ]
    )

    chain = prompt | llm

    try:
        verification = chain.invoke(
            {"new_q": question, "cached_q": best_match.question}
        )
        if verification and verification.is_match:
            logger.info(f"Cache HIT verified. Reason: {verification.reason}")
            return {
                "cache_hit": True,
                "generated_sql": best_match.generated_sql,
                "selected_tables": best_match.tables_used,
                "reasoning": f"Cache hit: matched with '{best_match.question}'",
            }
        else:
            reason = verification.reason if verification else "Parse failed"
            logger.info(f"Cache match rejected by LLM. Reason: {reason}")
    except Exception as e:
        logger.warning(f"Cache verification failed: {e}")

    return {"cache_hit": False}


def write_cache_feedback(state: dict, feedback_score: int = 1) -> str | None:
    """Writes a successful execution to the cache. Called by the API on thumbs up."""
    if not state.get("is_valid_sql") or not state.get("generated_sql"):
        logger.warning("Cannot cache: SQL is invalid or missing.")
        return None

    question = state.get("rewritten_question") or state.get("question")
    source_id = state.get("source_id")
    sql = state.get("generated_sql")
    tables = state.get("selected_tables", [])

    cache = SemanticCache()
    cache_id = cache.add(source_id, question, sql, tables, feedback_score)
    logger.info(f"Saved to cache with ID: {cache_id}")
    return cache_id


if __name__ == "__main__":
    # Demo using the record we inserted in Step 2
    state_hit = {
        "question": "What is the total revenue by category?",
        "source_id": "olist",
    }
    print("--- Testing Exact Match ---")
    res1 = cache_lookup_node(state_hit)
    print(f"Result: {res1}\n")

    state_miss = {
        "question": "What is the total revenue by category in 2018?",
        "source_id": "olist",
    }
    print("--- Testing Parameter Mismatch ---")
    res2 = cache_lookup_node(state_miss)
    print(f"Result: {res2}")
