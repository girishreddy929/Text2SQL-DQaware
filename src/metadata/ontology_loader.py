"""src/metadata/ontology_loader.py: Load ontology YAML into meta.ontology_terms."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml
from sqlalchemy import text

from src.common.db import get_admin_engine
from src.metadata.ontology_models import OntologyFile, OntologyTerm

ONTOLOGY_DIR = Path("config/ontology")

UPSERT_SQL = """
INSERT INTO meta.ontology_terms (
    term_id, source_id, term_name, term_type, definition,
    sql_expression, base_table, mapped_columns, synonyms, status, updated_at
) VALUES (
    :term_id, :source_id, :term_name, :term_type, :definition,
    :sql_expression, :base_table, :mapped_columns, :synonyms, :status, clock_timestamp()
)
ON CONFLICT (term_id) DO UPDATE SET
    term_name = EXCLUDED.term_name,
    term_type = EXCLUDED.term_type,
    definition = EXCLUDED.definition,
    sql_expression = EXCLUDED.sql_expression,
    base_table = EXCLUDED.base_table,
    mapped_columns = EXCLUDED.mapped_columns,
    synonyms = EXCLUDED.synonyms,
    status = EXCLUDED.status,
    updated_at = clock_timestamp()
"""


def load_ontology_file(source_id: str) -> list[OntologyTerm]:
    """Read and validate YAML file for source_id."""
    slug_source = source_id.replace(":", "_")
    path = ONTOLOGY_DIR / f"{slug_source}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Ontology file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return OntologyFile(**data).terms


def sync_ontology(source_id: str) -> int:
    """Upsert ontology terms into meta.ontology_terms in one transaction."""
    terms = load_ontology_file(source_id)
    if not terms:
        return 0

    engine = get_admin_engine()
    with engine.begin() as conn:
        params = [
            {
                "term_id": t.term_id,
                "source_id": t.source_id,
                "term_name": t.term_name,
                "term_type": t.term_type,
                "definition": t.definition,
                "sql_expression": t.sql_expression,
                "base_table": t.base_table,
                "mapped_columns": t.mapped_columns,
                "synonyms": t.synonyms,
                "status": t.status,
            }
            for t in terms
        ]
        conn.execute(text(UPSERT_SQL), params)
    return len(terms)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="olist")
    args = parser.parse_args()

    count = sync_ontology(args.source)
    print(
        f"Synced {count} ontology terms into meta.ontology_terms for '{args.source}'."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
