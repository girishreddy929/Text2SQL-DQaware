"""src/metadata/kg_loader.py: Persist Knowledge Graph nodes and edges into PostgreSQL."""

from __future__ import annotations

import argparse
import json
from sqlalchemy import text
from src.adapters.db.base import ColumnInfo
from src.common.db import get_admin_engine
from src.ingestion.build_domains import load_domains
from src.metadata.bird_fk import load_bird_fks
from src.metadata.kg_builder import build_kg_entities
from src.metadata.kg_infer import infer_joins


def fetch_source_data(conn, source_id: str) -> tuple[dict, list, list, list, list]:
    """Fetch domains, tables, columns, rules, and column objects for a source."""
    t_rows = (
        conn.execute(
            text(
                "SELECT schema_name, table_name, description FROM meta.tables WHERE source_id = :s"
            ),
            {"s": source_id},
        )
        .mappings()
        .all()
    )

    domains = {}
    if source_id == "olist":
        dom_specs = load_domains()
        domains = {
            d: [f"{d}.{t}" for t in spec.tables] for d, spec in dom_specs.items()
        }
    elif source_id.startswith("bird:"):
        db_id = source_id.split(":", 1)[1]
        domains = {db_id: [f"{r['schema_name']}.{r['table_name']}" for r in t_rows]}

    c_rows = (
        conn.execute(
            text(
                "SELECT schema_name, table_name, column_name, data_type, is_pii FROM meta.columns WHERE source_id = :s"
            ),
            {"s": source_id},
        )
        .mappings()
        .all()
    )

    r_rows = (
        conn.execute(
            text(
                "SELECT rule_id, schema_name, table_name, column_names, rule_type, dimension FROM dq.rules WHERE source_id = :s"
            ),
            {"s": source_id},
        )
        .mappings()
        .all()
    )

    cols_for_join = [
        ColumnInfo(
            r["schema_name"], r["table_name"], r["column_name"], r["data_type"], True
        )
        for r in c_rows
    ]
    return domains, list(t_rows), list(c_rows), list(r_rows), cols_for_join


def get_joins_for_source(conn, source_id: str, cols_for_join: list[ColumnInfo]):
    if source_id == "olist":
        return infer_joins(conn, cols_for_join, min_overlap=0.75)
    if source_id.startswith("bird:"):
        return load_bird_fks(source_id.split(":", 1)[1])
    return []


def load_kg(source_id: str = "olist") -> tuple[int, int]:
    """Build and insert all KG nodes and edges for source_id in one transaction."""
    engine = get_admin_engine()
    with engine.begin() as conn:
        domains, tables, columns, rules, cols_for_join = fetch_source_data(
            conn, source_id
        )
        joins = get_joins_for_source(conn, source_id, cols_for_join)
        nodes, edges = build_kg_entities(
            source_id, domains, tables, columns, rules, joins
        )

        conn.execute(
            text("DELETE FROM meta.kg_edges WHERE source_id = :s"), {"s": source_id}
        )
        conn.execute(
            text("DELETE FROM meta.kg_nodes WHERE source_id = :s"), {"s": source_id}
        )

        if nodes:
            node_params = [
                {
                    "nid": n.node_id,
                    "sid": n.source_id,
                    "type": n.node_type,
                    "name": n.name,
                    "props": json.dumps(n.properties),
                }
                for n in nodes
            ]
            conn.execute(
                text("""
                    INSERT INTO meta.kg_nodes (node_id, source_id, node_type, name, properties)
                    VALUES (:nid, :sid, :type, :name, CAST(:props AS jsonb))
                """),
                node_params,
            )

        if edges:
            edge_params = [
                {
                    "eid": e.edge_id,
                    "sid": e.source_id,
                    "type": e.edge_type,
                    "src": e.src_node_id,
                    "tgt": e.tgt_node_id,
                    "w": e.weight,
                    "props": json.dumps(e.properties),
                }
                for e in edges
            ]
            conn.execute(
                text("""
                    INSERT INTO meta.kg_edges (edge_id, source_id, edge_type, src_node_id, tgt_node_id, weight, properties)
                    VALUES (:eid, :sid, :type, :src, :tgt, :w, CAST(:props AS jsonb))
                """),
                edge_params,
            )

    return len(nodes), len(edges)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="olist")
    args = parser.parse_args()

    n_count, e_count = load_kg(args.source)
    print(
        f"Loaded Knowledge Graph for '{args.source}': {n_count} nodes, {e_count} edges."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
