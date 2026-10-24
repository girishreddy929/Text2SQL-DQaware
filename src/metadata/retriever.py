"""src/metadata/retriever.py: Hybrid and vector schema retriever."""

from __future__ import annotations

import argparse
from src.adapters.vectordb.base import SearchResult, VectorStore
from src.adapters.vectordb.pgvector import PostgresVectorStore
from src.common.db import get_admin_engine
from src.common.llm import get_embeddings
from src.common.llm_guard import call_resilient
from src.metadata.indexer_prep import truncate_and_normalize


class SchemaRetriever:
    """Retrieves relevant tables, columns, and metrics for a user query."""

    def __init__(self, store: VectorStore | None = None, embed_model=None):
        self.store = store or PostgresVectorStore(get_admin_engine())
        self.embed_model = embed_model or get_embeddings()

    def retrieve(
        self,
        query: str,
        source_id: str,
        k: int = 5,
        entity_types: list[str] | None = None,
    ) -> list[SearchResult]:
        raw_vec = call_resilient(self.embed_model.embed_query, query)
        q_vec_768 = truncate_and_normalize(raw_vec, target_dim=768)
        return self.store.similarity_search(
            query_vector=q_vec_768,
            k=k,
            source_id=source_id,
            entity_types=entity_types,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="olist")
    parser.add_argument(
        "--query", default="Which customers had late deliveries and high payments?"
    )
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    retriever = SchemaRetriever()
    results = retriever.retrieve(args.query, source_id=args.source, k=args.k)

    print(f"\nQuery: '{args.query}' (Source: {args.source})")
    print(f"Top {len(results)} matches:")
    for i, r in enumerate(results, 1):
        print(
            f"  {i}. [{r.entity_type.upper()}] {r.entity_name} (Score: {r.score:.4f})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
