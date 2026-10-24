"""src/metadata/ontology_kg_sync.py: Synchronize approved ontology terms into the Knowledge Graph."""

from __future__ import annotations

import argparse
import json

from sqlalchemy import text

from src.common.db import get_admin_engine
from src.metadata.kg_models import edge_id, node_id
from src.metadata.ontology_models import slug


def sync_ontology_to_kg(source_id: str) -> tuple[int, int]:
    """Project approved ontology terms into meta.kg_nodes and meta.kg_edges."""
    engine = get_admin_engine()
    with engine.begin() as conn:
        terms = (
            conn.execute(
                text("""
                SELECT term_id, term_name, term_type, definition, sql_expression,
                       base_table, mapped_columns, synonyms
                FROM meta.ontology_terms
                WHERE source_id = :s AND status = 'approved'
            """),
                {"s": source_id},
            )
            .mappings()
            .all()
        )

        if not terms:
            return 0, 0

        # Remove prior ontology nodes & edges for this source
        conn.execute(
            text(
                "DELETE FROM meta.kg_edges WHERE source_id = :s AND edge_type = 'measures'"
            ),
            {"s": source_id},
        )
        conn.execute(
            text(
                "DELETE FROM meta.kg_nodes WHERE source_id = :s AND node_type IN ('metric', 'business_term')"
            ),
            {"s": source_id},
        )

        nodes_to_insert = []
        edges_to_insert = []

        for t in terms:
            n_type = "metric" if t["term_type"] == "metric" else "business_term"
            nid = node_id(source_id, n_type, slug(t["term_name"]))
            n_props = {
                "definition": t["definition"],
                "sql_expression": t["sql_expression"],
                "mapped_columns": list(t["mapped_columns"]),
                "synonyms": list(t["synonyms"]),
            }
            nodes_to_insert.append(
                {
                    "nid": nid,
                    "sid": source_id,
                    "type": n_type,
                    "name": t["term_name"],
                    "props": json.dumps(n_props),
                }
            )

            tbl_nid = node_id(source_id, "table", t["base_table"])
            eid = edge_id(source_id, "measures", nid, tbl_nid)
            e_props = {"sql_expression": t["sql_expression"]}
            edges_to_insert.append(
                {
                    "eid": eid,
                    "sid": source_id,
                    "type": "measures",
                    "src": nid,
                    "tgt": tbl_nid,
                    "w": 1.0,
                    "props": json.dumps(e_props),
                }
            )

        conn.execute(
            text("""
                INSERT INTO meta.kg_nodes (node_id, source_id, node_type, name, properties)
                VALUES (:nid, :sid, :type, :name, CAST(:props AS jsonb))
            """),
            nodes_to_insert,
        )

        conn.execute(
            text("""
                INSERT INTO meta.kg_edges (edge_id, source_id, edge_type, src_node_id, tgt_node_id, weight, properties)
                VALUES (:eid, :sid, :type, :src, :tgt, :w, CAST(:props AS jsonb))
            """),
            edges_to_insert,
        )

    return len(nodes_to_insert), len(edges_to_insert)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="olist")
    args = parser.parse_args()

    n_cnt, e_cnt = sync_ontology_to_kg(args.source)
    print(
        f"Synced {n_cnt} ontology nodes and {e_cnt} 'measures' edges into KG for '{args.source}'."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
