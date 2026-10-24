"""src/metadata/kg_models.py: Data models and ID helpers for Knowledge Graph."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

NodeType = Literal["domain", "table", "column", "dq_rule", "business_term", "metric"]
EdgeType = Literal["contains", "has_column", "joins_with", "has_dq_rule", "synonym_of"]


def node_id(source_id: str, node_type: NodeType, *parts: str) -> str:
    """Deterministic node ID: e.g. 'olist:table:sales.orders'."""
    clean = ":".join(p.strip().lower() for p in parts if p.strip())
    return f"{source_id}:{node_type}:{clean}"


def edge_id(source_id: str, edge_type: EdgeType, src: str, tgt: str) -> str:
    """Deterministic edge ID: e.g. 'olist:joins_with:olist:table:sales.orders->...'."""
    return f"{source_id}:{edge_type}:{src}->{tgt}"


@dataclass(frozen=True)
class KGNode:
    node_id: str
    source_id: str
    node_type: NodeType
    name: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KGEdge:
    edge_id: str
    source_id: str
    edge_type: EdgeType
    src_node_id: str
    tgt_node_id: str
    weight: float = 1.0
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class JoinCandidate:
    src_table: str  # "schema.table"
    tgt_table: str  # "schema.table"
    src_col: str
    tgt_col: str
    overlap_pct: float = 0.0
    reason: str = ""
