# src/app/cache.py
import argparse
from pydantic import BaseModel
from sqlalchemy import text

from src.common.db import get_admin_engine
from src.common.llm import get_embeddings
from src.metadata.indexer_prep import truncate_and_normalize
from src.common.logging import get_logger

logger = get_logger(__name__)


class CacheEntry(BaseModel):
    id: str
    question: str
    generated_sql: str
    tables_used: list[str]
    similarity: float


class SemanticCache:
    def __init__(self, engine=None, embeddings=None):
        # We use admin_engine because t2s_reader is blocked from the app schema
        self.engine = engine or get_admin_engine()
        self.embeddings = embeddings or get_embeddings()

    def _embed(self, text_val: str) -> list[float]:
        """Embeds text, truncates to 768 dims, and L2 normalizes."""
        raw_vec = self.embeddings.embed_query(text_val)
        return truncate_and_normalize(raw_vec, 768)

    def add(
        self,
        source_id: str,
        question: str,
        generated_sql: str,
        tables_used: list[str],
        feedback_score: int = 1,
    ) -> str:
        """Adds a query to the semantic cache."""
        vec = self._embed(question)
        sql = """
            INSERT INTO app.semantic_cache 
            (source_id, question, generated_sql, tables_used, embedding, feedback_score)
            VALUES (:source_id, :question, :generated_sql, :tables_used, CAST(:embedding AS vector), :feedback_score)
            RETURNING id
        """
        with self.engine.begin() as conn:
            res = conn.execute(
                text(sql),
                {
                    "source_id": source_id,
                    "question": question,
                    "generated_sql": generated_sql,
                    "tables_used": tables_used,
                    "embedding": str(vec),
                    "feedback_score": feedback_score,
                },
            )
            return str(res.scalar())

    def search(
        self, source_id: str, question: str, limit: int = 3, threshold: float = 0.85
    ) -> list[CacheEntry]:
        """Searches for similar questions with positive feedback."""
        vec = self._embed(question)
        sql = """
            SELECT id, question, generated_sql, tables_used,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM app.semantic_cache
            WHERE source_id = :source_id
              AND feedback_score > 0
              AND 1 - (embedding <=> CAST(:embedding AS vector)) >= :threshold
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
        """
        with self.engine.connect() as conn:
            rows = (
                conn.execute(
                    text(sql),
                    {
                        "source_id": source_id,
                        "embedding": str(vec),
                        "threshold": threshold,
                        "limit": limit,
                    },
                )
                .mappings()
                .all()
            )

            return [
                CacheEntry(
                    id=str(r["id"]),
                    question=r["question"],
                    generated_sql=r["generated_sql"],
                    tables_used=r["tables_used"],
                    similarity=float(r["similarity"]),
                )
                for r in rows
            ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Semantic Cache")
    parser.add_argument("--source", default="olist", help="Source ID")
    args = parser.parse_args()

    cache = SemanticCache()

    q1 = "Show me the total revenue by product category"
    sql1 = "SELECT product_category_name, SUM(price) FROM sales.order_items JOIN catalog.products USING (product_id) GROUP BY 1"

    logger.info(f"Adding to cache: '{q1}'")
    cache_id = cache.add(
        args.source, q1, sql1, ["sales.order_items", "catalog.products"]
    )
    logger.info(f"Inserted with ID: {cache_id}")

    q2 = "What is the total revenue grouped by category?"
    logger.info(f"Searching cache for: '{q2}'")
    results = cache.search(args.source, q2)

    if results:
        for r in results:
            logger.info(
                f"Match: {r.similarity:.4f} | Q: {r.question} | SQL: {r.generated_sql}"
            )
    else:
        logger.info("No matches found.")
