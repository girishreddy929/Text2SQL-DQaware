"""src/metadata/kg_builder.py: Pure builder converting metadata, rules, and joins into KG entities."""

from __future__ import annotations

from typing import Any
from src.metadata.kg_models import JoinCandidate, KGEdge, KGNode, edge_id, node_id


def build_kg_entities(
    source_id: str,
    domains: dict[str, list[str]],  # domain_name -> list of "schema.table"
    tables: list[dict[str, Any]],  # schema_name, table_name, description
    columns: list[
        dict[str, Any]
    ],  # schema_name, table_name, column_name, data_type, is_pii
    rules: list[
        dict[str, Any]
    ],  # rule_id, schema_name, table_name, column_names, rule_type
    joins: list[JoinCandidate],
) -> tuple[list[KGNode], list[KGEdge]]:
    nodes: list[KGNode] = []
    edges: list[KGEdge] = []
    seen_nodes: set[str] = set()

    def add_node(n: KGNode) -> None:
        if n.node_id not in seen_nodes:
            seen_nodes.add(n.node_id)
            nodes.append(n)

    # 1. Domains & Table Containment
    for dom, tbl_list in domains.items():
        d_id = node_id(source_id, "domain", dom)
        add_node(KGNode(d_id, source_id, "domain", dom))
        for full_tbl in tbl_list:
            t_id = node_id(source_id, "table", full_tbl)
            edges.append(
                KGEdge(
                    edge_id(source_id, "contains", d_id, t_id),
                    source_id,
                    "contains",
                    d_id,
                    t_id,
                )
            )

    # 2. Tables & Columns
    for t in tables:
        full_t = f"{t['schema_name']}.{t['table_name']}"
        t_id = node_id(source_id, "table", full_t)
        add_node(
            KGNode(
                t_id,
                source_id,
                "table",
                full_t,
                {"description": t.get("description", "")},
            )
        )

    for c in columns:
        full_t = f"{c['schema_name']}.{c['table_name']}"
        full_c = f"{full_t}.{c['column_name']}"
        t_id = node_id(source_id, "table", full_t)
        c_id = node_id(source_id, "column", full_c)
        add_node(
            KGNode(
                c_id,
                source_id,
                "column",
                c["column_name"],
                {"data_type": c.get("data_type", ""), "is_pii": c.get("is_pii", False)},
            )
        )
        edges.append(
            KGEdge(
                edge_id(source_id, "has_column", t_id, c_id),
                source_id,
                "has_column",
                t_id,
                c_id,
            )
        )

    # 3. DQ Rules
    for r in rules:
        r_id = node_id(source_id, "dq_rule", r["rule_id"])
        add_node(
            KGNode(
                r_id,
                source_id,
                "dq_rule",
                r["rule_id"],
                {
                    "rule_type": r.get("rule_type", ""),
                    "dimension": r.get("dimension", ""),
                },
            )
        )
        full_t = f"{r['schema_name']}.{r['table_name']}"
        t_id = node_id(source_id, "table", full_t)
        edges.append(
            KGEdge(
                edge_id(source_id, "has_dq_rule", t_id, r_id),
                source_id,
                "has_dq_rule",
                t_id,
                r_id,
            )
        )

    # 4. Joins (Bidirectional joins_with edges)
    for j in joins:
        t1_id = node_id(source_id, "table", j.src_table)
        t2_id = node_id(source_id, "table", j.tgt_table)
        weight = round(2.0 - (j.overlap_pct / 100.0), 4)
        p1 = {
            "src_col": j.src_col,
            "tgt_col": j.tgt_col,
            "overlap_pct": j.overlap_pct,
            "reason": j.reason,
        }
        edges.append(
            KGEdge(
                edge_id(source_id, "joins_with", t1_id, t2_id),
                source_id,
                "joins_with",
                t1_id,
                t2_id,
                weight,
                p1,
            )
        )
        p2 = {
            "src_col": j.tgt_col,
            "tgt_col": j.src_col,
            "overlap_pct": j.overlap_pct,
            "reason": j.reason,
        }
        edges.append(
            KGEdge(
                edge_id(source_id, "joins_with", t2_id, t1_id),
                source_id,
                "joins_with",
                t2_id,
                t1_id,
                weight,
                p2,
            )
        )

    return nodes, edges
