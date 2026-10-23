"""Run:  python -m src.ingestion.build_domains
Reads config/domains.yaml, generates SQL (schemas, typed tables, INSERT..SELECT with casts),
writes it to sql/01_domain_schemas.sql so you can read exactly what ran, then executes it.
Safe to re-run: each domain schema is dropped and rebuilt.
NOTE: re-running drops the schemas, so re-run the role setup (Part B) afterwards."""

import re
import sys

import yaml
from pydantic import BaseModel
from sqlalchemy import text

from config.settings import PROJECT_ROOT
from src.common.db import get_admin_engine
from src.common.logging import get_logger

log = get_logger("build_domains")

DOMAINS_FILE = PROJECT_ROOT / "config" / "domains.yaml"
SCRIPT_FILE = PROJECT_ROOT / "sql" / "01_domain_schemas.sql"

IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")
INT_TYPES = {"smallint", "integer", "bigint"}


class TableSpec(BaseModel):
    source: str
    primary_key: list[str] = []
    columns: dict[str, str]


class DomainSpec(BaseModel):
    description: str
    tables: dict[str, TableSpec]


class DomainsConfig(BaseModel):
    domains: dict[str, DomainSpec]


def _check_ident(name: str) -> None:
    # Names go into generated SQL, so only allow plain lowercase identifiers.
    if not IDENT.match(name):
        raise ValueError(f"Unsafe or invalid identifier in domains.yaml: {name!r}")


def load_domains() -> dict[str, DomainSpec]:
    with open(DOMAINS_FILE, encoding="utf-8") as f:
        cfg = DomainsConfig.model_validate(yaml.safe_load(f))
    for schema, dom in cfg.domains.items():
        _check_ident(schema)
        for table, spec in dom.tables.items():
            _check_ident(table)
            _check_ident(spec.source)
            for col in spec.columns:
                _check_ident(col)
            for key in spec.primary_key:
                if key not in spec.columns:
                    raise ValueError(
                        f"{schema}.{table}: primary key {key!r} is not a column"
                    )
    return cfg.domains


def select_expr(col: str, col_type: str) -> str:
    """How to turn a raw TEXT column into its proper type."""
    base = col_type.split("(")[0].strip().lower()
    if base == "text":
        return col
    if base in INT_TYPES:  # numeric hop tolerates values like '40.0'
        return f"NULLIF(trim({col}), '')::numeric::{col_type}"
    return f"NULLIF(trim({col}), '')::{col_type}"


def build_statements(domains: dict[str, DomainSpec]) -> list[str]:
    stmts: list[str] = []
    for schema, dom in domains.items():
        stmts.append(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        stmts.append(f"CREATE SCHEMA {schema}")
        description = dom.description.replace("'", "''")
        stmts.append(f"COMMENT ON SCHEMA {schema} IS '{description}'")
        for table, spec in dom.tables.items():
            cols_ddl = ",\n  ".join(f"{c} {t}" for c, t in spec.columns.items())
            pk = (
                f",\n  PRIMARY KEY ({', '.join(spec.primary_key)})"
                if spec.primary_key
                else ""
            )
            stmts.append(f"CREATE TABLE {schema}.{table} (\n  {cols_ddl}{pk}\n)")
            col_list = ", ".join(spec.columns)
            select_list = ",\n  ".join(
                select_expr(c, t) for c, t in spec.columns.items()
            )
            stmts.append(
                f"INSERT INTO {schema}.{table} ({col_list})\n"
                f"SELECT\n  {select_list}\nFROM raw.{spec.source}"
            )
    return stmts


def check_raw_columns(
    conn, domains: dict[str, DomainSpec]
) -> tuple[list[str], list[str]]:
    """Catch YAML/raw mismatches BEFORE touching anything.
    Returns (problems, warnings). Problems stop the build; warnings only inform."""
    problems: list[str] = []
    warnings: list[str] = []
    for schema, dom in domains.items():
        for table, spec in dom.tables.items():
            rows = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'raw' AND table_name = :t ORDER BY ordinal_position"
                ),
                {"t": spec.source},
            )
            have = [r[0] for r in rows]
            if not have:
                problems.append(
                    f"raw.{spec.source} does not exist (run load_raw first)"
                )
                continue
            for col in spec.columns:
                if col not in have:
                    problems.append(
                        f"{schema}.{table}: column '{col}' not found in raw.{spec.source}"
                    )
            for col in have:
                if col not in spec.columns:
                    warnings.append(
                        f"{schema}.{table}: raw column '{col}' is NOT in domains.yaml and would be left out"
                    )
    return problems, warnings


def main() -> int:
    domains = load_domains()
    engine = get_admin_engine()

    with engine.connect() as conn:
        problems, warnings = check_raw_columns(conn, domains)
    for w in warnings:
        print("WARNING:", w)
    if problems:
        print("Problems found (nothing was changed):")
        for p in problems:
            print("  -", p)
        return 1

    stmts = build_statements(domains)
    header = (
        "-- GENERATED by src/ingestion/build_domains.py from config/domains.yaml.\n"
        "-- Do not edit by hand; change domains.yaml and re-run.\n\n"
    )
    SCRIPT_FILE.write_text(header + ";\n\n".join(stmts) + ";\n", encoding="utf-8")
    log.info(
        "Wrote %s (%d statements)", SCRIPT_FILE.relative_to(PROJECT_ROOT), len(stmts)
    )

    with engine.begin() as conn:  # all-or-nothing
        for stmt in stmts:
            conn.exec_driver_sql(stmt)
        conn.exec_driver_sql("ANALYZE")

    print("\nDomain build summary")
    print("-" * 70)
    print(f"{'table':<34}{'rows':>12}{'raw rows':>12}  status")
    all_ok = True
    with engine.connect() as conn:
        for schema, dom in domains.items():
            for table, spec in dom.tables.items():
                new = conn.execute(
                    text(f"SELECT count(*) FROM {schema}.{table}")
                ).scalar_one()
                old = conn.execute(
                    text(f"SELECT count(*) FROM raw.{spec.source}")
                ).scalar_one()
                ok = new == old
                all_ok &= ok
                print(
                    f"{schema + '.' + table:<34}{new:>12,}{old:>12,}  {'OK' if ok else 'MISMATCH'}"
                )
    print("-" * 70)
    print(
        "All domain tables match raw row counts"
        if all_ok
        else "Some tables need attention"
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
