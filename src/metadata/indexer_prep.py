"""src/metadata/indexer_prep.py: Format metadata elements into embedding text payloads."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any
from src.metadata.kg_models import node_id


@dataclass
class RawEmbeddingItem:
    id: str
    source_id: str
    entity_type: str  # table, column, metric, business_term
    entity_name: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def truncate_and_normalize(vec: list[float], target_dim: int = 768) -> list[float]:
    """Truncate Matryoshka vector to target_dim and re-normalize to unit length."""
    sub = vec[:target_dim]
    norm = math.sqrt(sum(x * x for x in sub))
    return [x / norm for x in sub] if norm > 0 else sub


def format_table_payload(
    source_id: str, t: dict[str, Any], col_names: list[str]
) -> RawEmbeddingItem:
    full_table = f"{t['schema_name']}.{t['table_name']}"
    nid = node_id(source_id, "table", full_table)
    syns = ", ".join(t.get("synonyms") or [])
    cols = ", ".join(col_names)
    text = (
        f"Table: {full_table}. Description: {t.get('description', '')}. "
        f"Synonyms: {syns or 'none'}. Columns: {cols}."
    )
    return RawEmbeddingItem(
        id=nid,
        source_id=source_id,
        entity_type="table",
        entity_name=full_table,
        text=text,
        metadata={"schema": t["schema_name"], "table": t["table_name"]},
    )


def format_column_payload(source_id: str, c: dict[str, Any]) -> RawEmbeddingItem:
    full_table = f"{c['schema_name']}.{c['table_name']}"
    nid = node_id(source_id, "column", f"{full_table}.{c['column_name']}")
    syns = ", ".join(c.get("synonyms") or [])
    text = (
        f"Column: {c['column_name']} in table {full_table}. Type: {c['data_type']}. "
        f"Role: {c.get('column_role', 'dimension')}. Description: {c.get('description', '')}. "
        f"Synonyms: {syns or 'none'}."
    )
    return RawEmbeddingItem(
        id=nid,
        source_id=source_id,
        entity_type="column",
        entity_name=f"{full_table}.{c['column_name']}",
        text=text,
        metadata={
            "schema": c["schema_name"],
            "table": c["table_name"],
            "column": c["column_name"],
        },
    )


def format_ontology_payload(source_id: str, o: dict[str, Any]) -> RawEmbeddingItem:
    etype = "metric" if o["term_type"] == "metric" else "business_term"
    nid = o.get("term_id") or node_id(source_id, etype, o["term_name"])
    syns = ", ".join(o.get("synonyms") or [])
    text = (
        f"Business {o['term_type']}: {o['term_name']}. Base table: {o['base_table']}. "
        f"Definition: {o['definition']}. Formula: {o['sql_expression']}. Synonyms: {syns or 'none'}."
    )
    return RawEmbeddingItem(
        id=nid,
        source_id=source_id,
        entity_type=etype,
        entity_name=o["term_name"],
        text=text,
        metadata={"base_table": o["base_table"], "sql_expression": o["sql_expression"]},
    )
