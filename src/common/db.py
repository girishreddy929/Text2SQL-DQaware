"""Database access. Two engines (admin for setup/loading, reader for agents)
plus a factory that returns a DBConnector for the configured DB_BACKEND."""

from functools import lru_cache

from sqlalchemy import Engine, create_engine, text

from config.settings import get_settings


@lru_cache(maxsize=1)
def get_admin_engine() -> Engine:
    """Full-rights engine. ONLY for setup, loading and DQ/metadata writes."""
    return create_engine(get_settings().admin_db_url, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_reader_engine() -> Engine:
    """Read-only engine (role t2s_reader). The ONLY engine agents may use."""
    return create_engine(get_settings().reader_db_url, pool_pre_ping=True)


def ping() -> bool:
    with get_admin_engine().connect() as conn:
        return conn.execute(text("SELECT 1")).scalar_one() == 1


def get_connector(read_only: bool = True):
    """Factory: returns the DBConnector for DB_BACKEND (postgres today)."""
    backend = get_settings().db_backend.lower()
    if backend == "postgres":
        from src.adapters.db.postgres import (
            PostgresConnector,
        )  # lazy: avoids circular import

        engine = get_reader_engine() if read_only else get_admin_engine()
        return PostgresConnector(engine)
    raise ValueError(f"Unknown DB_BACKEND '{backend}'. Supported: postgres")
