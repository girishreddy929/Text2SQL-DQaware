"""PostgreSQL implementation of DBConnector (SQLAlchemy + psycopg 3)."""

import re
import time

from sqlalchemy import Engine, text

from src.adapters.db.base import ColumnInfo, DBConnector, QueryResult

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class PostgresConnector(DBConnector):
    dialect = "postgres"

    def __init__(self, engine: Engine):
        self._engine = engine

    def run_query(
        self, sql, params=None, *, search_path=None, max_rows=None
    ) -> QueryResult:
        started = time.perf_counter()
        with self._engine.connect() as conn:
            if search_path:
                schemas = (
                    [search_path] if isinstance(search_path, str) else list(search_path)
                )
                for name in schemas:
                    if not _IDENT.match(name):
                        raise ValueError(
                            f"Invalid schema name for search_path: {name!r}"
                        )
                # SET LOCAL: applies to this transaction only, so it can't leak between questions
                conn.exec_driver_sql("SET LOCAL search_path TO " + ", ".join(schemas))

            result = conn.execute(text(sql), params or {})
            if not result.returns_rows:
                return QueryResult(
                    sql, [], [], False, (time.perf_counter() - started) * 1000
                )

            columns = list(result.keys())
            if max_rows is None:
                rows, truncated = [tuple(r) for r in result.fetchall()], False
            else:
                fetched = result.fetchmany(max_rows + 1)
                truncated = len(fetched) > max_rows
                rows = [tuple(r) for r in fetched[:max_rows]]
        return QueryResult(
            sql, columns, rows, truncated, (time.perf_counter() - started) * 1000
        )

    def list_columns(self, schemas) -> list[ColumnInfo]:
        # information_schema only shows objects this role may access: a handy safety net.
        query = text(
            "SELECT table_schema, table_name, column_name, data_type, is_nullable "
            "FROM information_schema.columns WHERE table_schema = ANY(:schemas) "
            "ORDER BY table_schema, table_name, ordinal_position"
        )
        with self._engine.connect() as conn:
            rows = conn.execute(query, {"schemas": list(schemas)}).all()
        return [ColumnInfo(r[0], r[1], r[2], r[3], r[4] == "YES") for r in rows]

    def close(self) -> None:
        self._engine.dispose()
