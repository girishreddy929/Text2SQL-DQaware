"""src/metadata/indexer.py: Embed and index schema and ontology metadata."""

from __future__ import annotations

import argparse
from sqlalchemy import text
from src.adapters.vectordb.base import VectorItem
from src.adapters.vectordb.pgvector import PostgresVectorStore
from src.common.db import get_admin_engine
from src.common.llm import get_embeddings
from src.common.llm_guard import call_resilient
from src.metadata.indexer_prep import (
    RawEmbeddingItem,
    format_column_payload,
    format_ontology_payload,
    format_table_payload,
    truncate_and_normalize,
)


def fetch_raw_items(conn, source_id: str) -> list[RawEmbeddingItem]:
    """Collect tables, columns, and ontology terms for a source."""
    items: list[RawEmbeddingItem] = []

    # Tables & column names
    tbls = (
        conn.execute(
            text(
                "SELECT schema_name, table_name, description, synonyms FROM meta.tables WHERE source_id = :s"
            ),
            {"s": source_id},
        )
        .mappings()
        .all()
    )

    cols = (
        conn.execute(
            text("""
            SELECT schema_name, table_name, column_name, data_type, column_role, description, synonyms
            FROM meta.columns WHERE source_id = :s
        """),
            {"s": source_id},
        )
        .mappings()
        .all()
    )

    tbl_to_cols: dict[tuple[str, str], list[str]] = {}
    for c in cols:
        tbl_to_cols.setdefault((c["schema_name"], c["table_name"]), []).append(
            c["column_name"]
        )

    for t in tbls:
        c_names = tbl_to_cols.get((t["schema_name"], t["table_name"]), [])
        items.append(format_table_payload(source_id, t, c_names))

    for c in cols:
        items.append(format_column_payload(source_id, c))

    # Ontology Terms
    terms = (
        conn.execute(
            text("""
            SELECT term_id, term_name, term_type, definition, sql_expression, base_table, synonyms
            FROM meta.ontology_terms WHERE source_id = :s AND status = 'approved'
        """),
            {"s": source_id},
        )
        .mappings()
        .all()
    )

    for o in terms:
        items.append(format_ontology_payload(source_id, o))

    return items


def index_source(source_id: str = "olist", batch_size: int = 50) -> int:
    """Generate 768-dim embeddings and store in pgvector."""
    engine = get_admin_engine()
    with engine.connect() as conn:
        raw_items = fetch_raw_items(conn, source_id)

    if not raw_items:
        return 0

    embed_model = get_embeddings()
    vector_items: list[VectorItem] = []

    for i in range(0, len(raw_items), batch_size):
        batch = raw_items[i : i + batch_size]
        texts = [it.text for it in batch]
        raw_vectors = call_resilient(embed_model.embed_documents, texts)

        for it, raw_v in zip(batch, raw_vectors):
            v_768 = truncate_and_normalize(raw_v, 768)
            vector_items.append(
                VectorItem(
                    id=it.id,
                    source_id=it.source_id,
                    entity_type=it.entity_type,
                    entity_name=it.entity_name,
                    content=it.text,
                    embedding=v_768,
                    metadata=it.metadata,
                )
            )

    store = PostgresVectorStore(engine)
    store.delete_by_source(source_id)
    return store.add_items(vector_items)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="olist")
    args = parser.parse_args()

    count = index_source(args.source)
    print(f"Indexed {count} schema/ontology elements for '{args.source}' in pgvector.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
