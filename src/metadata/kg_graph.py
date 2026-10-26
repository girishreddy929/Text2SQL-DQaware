# src/metadata/kg_graph.py
"""src/metadata/kg_graph.py: NetworkX graph loader and join path finder."""

from __future__ import annotations

import argparse
import networkx as nx
from sqlalchemy import text
from src.common.db import get_admin_engine
from src.metadata.kg_models import node_id


def load_graph(engine, source_id: str) -> nx.DiGraph:
    """Load nodes and edges for source_id into a NetworkX DiGraph."""
    G = nx.DiGraph()
    with engine.connect() as conn:
        nodes = (
            conn.execute(
                text(
                    "SELECT node_id, node_type, name, properties FROM meta.kg_nodes WHERE source_id = :s"
                ),
                {"s": source_id},
            )
            .mappings()
            .all()
        )
        for n in nodes:
            G.add_node(
                n["node_id"], type=n["node_type"], name=n["name"], **n["properties"]
            )

        edges = (
            conn.execute(
                text(
                    "SELECT edge_id, edge_type, src_node_id, tgt_node_id, weight, properties FROM meta.kg_edges WHERE source_id = :s"
                ),
                {"s": source_id},
            )
            .mappings()
            .all()
        )
        for e in edges:
            G.add_edge(
                e["src_node_id"],
                e["tgt_node_id"],
                edge_id=e["edge_id"],
                type=e["edge_type"],
                weight=float(e["weight"]),
                **e["properties"],
            )
    return G


def find_join_path(
    G: nx.DiGraph, source_id: str, src_table: str, tgt_table: str
) -> list[dict]:
    """Find shortest join path between two tables using joins_with edges."""
    src_id = node_id(source_id, "table", src_table)
    tgt_id = node_id(source_id, "table", tgt_table)

    if src_id not in G or tgt_id not in G:
        return []

    join_edges = [
        (u, v, d) for u, v, d in G.edges(data=True) if d.get("type") == "joins_with"
    ]
    join_subgraph = nx.DiGraph()
    for u, v, d in join_edges:
        join_subgraph.add_edge(u, v, **d)

    try:
        path = nx.shortest_path(
            join_subgraph, source=src_id, target=tgt_id, weight="weight"
        )
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []

    hops = []
    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        edge_data = join_subgraph[u][v]
        hops.append(
            {
                "from_table": G.nodes[u]["name"],
                "to_table": G.nodes[v]["name"],
                "from_col": edge_data["src_col"],
                "to_col": edge_data["tgt_col"],
                "overlap_pct": edge_data.get("overlap_pct", 100.0),
            }
        )
    return hops


def format_join_sql(hops: list[dict]) -> str:
    """Render SQL JOIN clauses from path hops."""
    return " ".join(
        f"JOIN {hop['to_table']} ON {hop['from_table']}.{hop['from_col']} = {hop['to_table']}.{hop['to_col']}"
        for hop in hops
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="olist")
    parser.add_argument("--from-table", default="customer.customers")
    parser.add_argument("--to-table", default="catalog.products")
    args = parser.parse_args()

    engine = get_admin_engine()
    G = load_graph(engine, args.source)
    print(
        f"Loaded graph with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges."
    )

    hops = find_join_path(G, args.source, args.from_table, args.to_table)
    if not hops:
        print(f"No path between {args.from_table} and {args.to_table}")
        return 1

    print(f"\nShortest join path ({len(hops)} hops):")
    for i, h in enumerate(hops, 1):
        print(
            f"  {i}. {h['from_table']}.{h['from_col']} -> {h['to_table']}.{h['to_col']} ({h['overlap_pct']}%)"
        )
    print("\nGenerated SQL JOIN Clause:")
    print(f"  FROM {args.from_table} {format_join_sql(hops)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
