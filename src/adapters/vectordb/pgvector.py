"""src/adapters/vectordb/pgvector.py: PostgreSQL pgvector adapter."""

from __future__ import annotations

import json

from sqlalchemy import text

from src.adapters.vectordb.base import SearchResult, VectorItem, VectorStore
from src.common.db import get_admin_engine


class PostgresVectorStore(VectorStore):
    """PostgreSQL + pgvector implementation."""

    def __init__(self, engine=None):
        self.engine = engine or get_admin_engine()

    def add_items(self, items: list[VectorItem]) -> int:
        if not items:
            return 0
        sql = """
        INSERT INTO meta.schema_embeddings (
            id, source_id, entity_type, entity_name, content, metadata, embedding, created_at
        ) VALUES (
            :id, :source_id, :entity_type, :entity_name, :content, CAST(:metadata AS jsonb),
            CAST(:embedding AS vector), clock_timestamp()
        )
        ON CONFLICT (id) DO UPDATE SET
            content = EXCLUDED.content,
            metadata = EXCLUDED.metadata,
            embedding = EXCLUDED.embedding,
            created_at = clock_timestamp();
        """
        params = [
            {
                "id": it.id,
                "source_id": it.source_id,
                "entity_type": it.entity_type,
                "entity_name": it.entity_name,
                "content": it.content,
                "metadata": json.dumps(it.metadata),
                "embedding": str(it.embedding),
            }
            for it in items
        ]
        with self.engine.begin() as conn:
            conn.execute(text(sql), params)
        return len(items)

    def similarity_search(
        self,
        query_vector: list[float],
        k: int = 5,
        source_id: str | None = None,
        entity_types: list[str] | None = None,
    ) -> list[SearchResult]:
        filters = []
        params = {"vec": str(query_vector), "k": k}
        if source_id:
            filters.append("source_id = :sid")
            params["sid"] = source_id
        if entity_types:
            filters.append("entity_type = ANY(:etypes)")
            params["etypes"] = entity_types

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        sql = f"""
        SELECT id, source_id, entity_type, entity_name, content, metadata,
               1.0 - (embedding <=> CAST(:vec AS vector)) AS similarity
        FROM meta.schema_embeddings
        {where_clause}
        ORDER BY embedding <=> CAST(:vec AS vector)
        LIMIT :k;
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()

        return [
            SearchResult(
                id=r["id"],
                source_id=r["source_id"],
                entity_type=r["entity_type"],
                entity_name=r["entity_name"],
                content=r["content"],
                score=float(r["similarity"]),
                metadata=dict(r["metadata"]) if r["metadata"] else {},
            )
            for r in rows
        ]

    def delete_by_source(self, source_id: str) -> int:
        sql = "DELETE FROM meta.schema_embeddings WHERE source_id = :sid"
        with self.engine.begin() as conn:
            res = conn.execute(text(sql), {"sid": source_id})
            return res.rowcount or 0
