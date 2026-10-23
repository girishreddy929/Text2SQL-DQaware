"""Run:  python -m src.ingestion.setup_roles
Creates (or updates) the read-only role t2s_reader. Safe to re-run.
IMPORTANT: re-run this after every build_domains run (rebuilding drops schema grants)."""

import sys

from psycopg import sql
from sqlalchemy import text

from config.settings import get_settings
from src.common.db import get_admin_engine
from src.ingestion.build_domains import load_domains

ROLE = "t2s_reader"
STATEMENT_TIMEOUT = "30s"
HIDDEN_SCHEMAS = [
    "raw",
    "dq",
    "meta",
    "app",
]  # agents get no access unless granted in later blocks


def main() -> int:
    settings = get_settings()
    schemas = list(load_domains().keys())
    password = settings.t2s_reader_password.get_secret_value()
    role = sql.Identifier(ROLE)
    database = sql.Identifier(settings.postgres_db)

    engine = get_admin_engine()
    with engine.begin() as conn:
        pg = conn.connection.driver_connection  # psycopg connection, same transaction

        exists = conn.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROLE}
        ).scalar_one_or_none()
        verb = sql.SQL("ALTER" if exists else "CREATE")
        pg.execute(
            sql.SQL("{} ROLE {} LOGIN PASSWORD {}").format(
                verb, role, sql.Literal(password)
            )
        )

        pg.execute(
            sql.SQL("ALTER ROLE {} SET statement_timeout = {}").format(
                role, sql.Literal(STATEMENT_TIMEOUT)
            )
        )
        pg.execute(
            sql.SQL(
                "ALTER ROLE {} SET idle_in_transaction_session_timeout = '60s'"
            ).format(role)
        )
        pg.execute(
            sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(role)
        )
        pg.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(database, role))

        for hidden in HIDDEN_SCHEMAS:
            found = conn.execute(
                text("SELECT 1 FROM pg_namespace WHERE nspname = :n"), {"n": hidden}
            ).scalar_one_or_none()
            if found:
                ident = sql.Identifier(hidden)
                pg.execute(
                    sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA {} FROM {}").format(
                        ident, role
                    )
                )
                pg.execute(
                    sql.SQL("REVOKE ALL ON SCHEMA {} FROM {}").format(ident, role)
                )

        for schema in schemas:
            ident = sql.Identifier(schema)
            pg.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(ident, role))
            pg.execute(
                sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(
                    ident, role
                )
            )
            pg.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT SELECT ON TABLES TO {}"
                ).format(ident, role)
            )

    print(f"Role {ROLE}: {'updated' if exists else 'created'}")
    print(
        f"  statement_timeout = {STATEMENT_TIMEOUT}, default_transaction_read_only = on"
    )
    print(f"  SELECT granted on schemas: {', '.join(schemas)}")
    print(f"  no access to: {', '.join(HIDDEN_SCHEMAS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
