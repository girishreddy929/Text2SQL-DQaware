# src/ingestion/setup_roles.py
"""Role setup: creates t2s_reader role, grants domain schemas, and gives read-only access to DQ views."""

import sys
from sqlalchemy import text

from config.settings import get_settings
from src.common.db import get_admin_engine, get_reader_engine
from src.common.logging import get_logger
from src.ingestion.build_domains import load_domains

logger = get_logger("ingestion.setup_roles")

ROLE = "t2s_reader"
STATEMENT_TIMEOUT = "30s"

SETUP_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '{role}') THEN
        CREATE ROLE {role} WITH LOGIN PASSWORD '{password}';
    ELSE
        ALTER ROLE {role} WITH PASSWORD '{password}';
    END IF;
END
$$;

ALTER ROLE {role} SET statement_timeout = '{timeout}';
ALTER ROLE {role} SET idle_in_transaction_session_timeout = '60s';
ALTER ROLE {role} SET default_transaction_read_only = on;

GRANT CONNECT ON DATABASE {db} TO {role};
"""

RESTRICT_AND_DQ_SQL = """
-- Strictly revoke sensitive internal schemas
REVOKE ALL ON SCHEMA raw, meta, app FROM {role};
REVOKE ALL ON ALL TABLES IN SCHEMA raw, meta, app FROM {role};
REVOKE ALL ON SCHEMA dq FROM {role};
REVOKE ALL ON ALL TABLES IN SCHEMA dq FROM {role};

-- Grant selective read access to curated DQ summary views only
GRANT USAGE ON SCHEMA dq TO {role};
GRANT SELECT ON dq.latest_results TO {role};
GRANT SELECT ON dq.latest_profiles TO {role};
"""

GRANT_SCHEMA_SQL = """
GRANT USAGE ON SCHEMA {schema} TO {role};
GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO {role};
ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT SELECT ON TABLES TO {role};
"""


def setup_roles() -> None:
    settings = get_settings()
    engine = get_admin_engine()
    domains = load_domains()

    logger.info("Configuring role '%s'...", ROLE)
    with engine.begin() as conn:
        conn.execute(
            text(
                SETUP_SQL.format(
                    role=ROLE,
                    password=settings.t2s_reader_password.get_secret_value(),
                    timeout=STATEMENT_TIMEOUT,
                    db=settings.postgres_db,
                )
            )
        )

        conn.execute(text(RESTRICT_AND_DQ_SQL.format(role=ROLE)))

        for domain_name in domains.keys():
            conn.execute(text(GRANT_SCHEMA_SQL.format(schema=domain_name, role=ROLE)))

    logger.info("Role '%s' successfully updated and domain privileges granted.", ROLE)

    # Verification as t2s_reader
    reader = get_reader_engine()
    with reader.connect() as conn:
        res = conn.execute(text("SELECT count(*) FROM dq.latest_results")).scalar()
        logger.info(
            "Verification check: t2s_reader read %d rows from dq.latest_results", res
        )


def main() -> int:
    try:
        setup_roles()
        return 0
    except Exception as exc:
        logger.error("Failed to setup roles: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
