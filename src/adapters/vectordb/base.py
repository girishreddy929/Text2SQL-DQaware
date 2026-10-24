"""src/adapters/vectordb/base.py: Abstract VectorStore interface for TrustSQL."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VectorItem:
    id: str
    source_id: str
    entity_type: str  # table, column, metric, business_term
    entity_name: str
    content: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    id: str
    source_id: str
    entity_type: str
    entity_name: str
    content: str
    score: float  # Cosine similarity [0.0 - 1.0]
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore(ABC):
    """Abstract Vector Store contract."""

    @abstractmethod
    def add_items(self, items: list[VectorItem]) -> int:
        """Upsert a list of embedded vector items."""
        ...

    @abstractmethod
    def similarity_search(
        self,
        query_vector: list[float],
        k: int = 5,
        source_id: str | None = None,
        entity_types: list[str] | None = None,
    ) -> list[SearchResult]:
        """Retrieve top-k similar items ranked by cosine similarity."""
        ...

    @abstractmethod
    def delete_by_source(self, source_id: str) -> int:
        """Remove all records for a source."""
        ...
