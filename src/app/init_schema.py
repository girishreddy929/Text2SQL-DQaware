# src/app/init_schema.py
import argparse
import sys
from pathlib import Path
from sqlalchemy import text
from src.common.db import get_admin_engine
from src.common.logging import get_logger

logger = get_logger(__name__)

SQL_FILE = Path("sql/08_app_schema.sql")
RESET_SQL = "DROP SCHEMA IF EXISTS app CASCADE;"


def init_app_schema(reset: bool = False) -> int:
    engine = get_admin_engine()

    if not SQL_FILE.exists():
        logger.error(f"Missing SQL file: {SQL_FILE}")
        return 1

    sql_script = SQL_FILE.read_text(encoding="utf-8")

    try:
        with engine.begin() as conn:
            if reset:
                logger.info("Resetting app schema...")
                conn.execute(text(RESET_SQL))

            logger.info(f"Applying {SQL_FILE}...")
            # psycopg 3 driver allows multiple statements if no parameters are bound
            conn.connection.driver_connection.execute(sql_script)

        # Verify creation and t2s_reader access
        with engine.connect() as conn:
            # Check table exists
            res = conn.execute(
                text("""
                SELECT count(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'app' AND table_name = 'semantic_cache'
            """)
            ).scalar()

            if res != 1:
                logger.error("app.semantic_cache table was not created successfully.")
                return 1

            # Check t2s_reader access (should be blocked)
            has_usage = conn.execute(
                text("""
                SELECT has_schema_privilege('t2s_reader', 'app', 'USAGE')
            """)
            ).scalar()

            if has_usage:
                logger.error("SECURITY ALERT: t2s_reader has USAGE on app schema!")
                return 1

        logger.info(
            "App schema initialized successfully. t2s_reader is correctly blocked."
        )
        return 0

    except Exception as e:
        logger.error(f"Failed to initialize app schema: {e}")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Initialize the app schema for cache/history."
    )
    parser.add_argument(
        "--reset", action="store_true", help="Drop the app schema before creating"
    )
    args = parser.parse_args()

    sys.exit(init_app_schema(reset=args.reset))
