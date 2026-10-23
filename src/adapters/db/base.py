"""Thin database interface. Agents talk to a DBConnector, never to a specific database."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass
class QueryResult:
    sql: str
    columns: list[str]
    rows: list[tuple]
    truncated: bool  # True if more rows existed than max_rows
    elapsed_ms: float

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=self.columns)


@dataclass(frozen=True)
class ColumnInfo:
    schema: str
    table: str
    column: str
    data_type: str
    is_nullable: bool


class DBConnector(ABC):
    dialect: str = "unknown"  # used later for sqlglot dialect selection

    @abstractmethod
    def run_query(
        self,
        sql: str,
        params: dict | None = None,
        *,
        search_path: str | list[str] | None = None,
        max_rows: int | None = None,
    ) -> QueryResult:
        """Run ONE statement and return rows. Never commits."""

    @abstractmethod
    def list_columns(self, schemas: list[str]) -> list[ColumnInfo]:
        """Columns visible to this connection in the given schemas."""

    @abstractmethod
    def close(self) -> None:
        """Release connections."""

    def list_tables(self, schemas: list[str]) -> list[tuple[str, str]]:
        return sorted({(c.schema, c.table) for c in self.list_columns(schemas)})
