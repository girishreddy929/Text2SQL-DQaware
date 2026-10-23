"""Run:  python -m src.ingestion.load_raw
Loads every Olist CSV from data/raw into schema `raw`, UNTOUCHED:
  * every column is TEXT (no type guessing, so a bad value can't break the load)
  * unquoted empty CSV fields become NULL (Postgres COPY behaviour)
Safe to re-run: each table is dropped and rebuilt."""

import csv
import sys
import time

from sqlalchemy import text

from config.settings import PROJECT_ROOT
from src.common.db import get_admin_engine
from src.common.logging import get_logger

log = get_logger("load_raw")

RAW_DIR = PROJECT_ROOT / "data" / "raw"
CHUNK_BYTES = 1024 * 1024  # stream the file to Postgres 1 MB at a time

# csv file -> (table name in schema raw, expected row count)
TABLES = {
    "olist_customers_dataset.csv": ("customers", 99441),
    "olist_geolocation_dataset.csv": ("geolocation", 1000163),
    "olist_order_items_dataset.csv": ("order_items", 112650),
    "olist_order_payments_dataset.csv": ("order_payments", 103886),
    "olist_order_reviews_dataset.csv": ("order_reviews", 99224),
    "olist_orders_dataset.csv": ("orders", 99441),
    "olist_products_dataset.csv": ("products", 32951),
    "olist_sellers_dataset.csv": ("sellers", 3095),
    "product_category_name_translation.csv": ("category_translation", 71),
    "olist_marketing_qualified_leads_dataset.csv": ("qualified_leads", 8000),
    "olist_closed_deals_dataset.csv": ("closed_deals", 842),
}


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def read_header(path) -> list[str]:
    with open(path, newline="", encoding="utf-8-sig") as f:  # utf-8-sig strips a BOM
        return [c.strip() for c in next(csv.reader(f))]


def load_table(conn, csv_name: str, table: str) -> int:
    """Rebuild raw.<table> from the CSV and return its row count."""
    path = RAW_DIR / csv_name
    columns = read_header(path)
    column_ddl = ", ".join(f"{quote_ident(c)} TEXT" for c in columns)

    conn.execute(text(f"DROP TABLE IF EXISTS raw.{table}"))
    conn.execute(text(f"CREATE TABLE raw.{table} ({column_ddl})"))

    # COPY needs the underlying psycopg connection (same transaction as above).
    pg_conn = conn.connection.driver_connection
    copy_sql = (
        f"COPY raw.{table} FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')"
    )
    with pg_conn.cursor() as cur:
        with cur.copy(copy_sql) as copy:
            with open(path, "rb") as f:
                while chunk := f.read(CHUNK_BYTES):
                    copy.write(chunk)

    return conn.execute(text(f"SELECT count(*) FROM raw.{table}")).scalar_one()


def main() -> int:
    missing = [name for name in TABLES if not (RAW_DIR / name).exists()]
    if missing:
        print("Missing CSV files (run python -m src.ingestion.download first):")
        for name in missing:
            print("  -", name)
        return 1

    engine = get_admin_engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS raw"))

    rows = []
    for csv_name, (table, expected) in TABLES.items():
        started = time.time()
        try:
            with engine.begin() as conn:  # one transaction per table
                loaded = load_table(conn, csv_name, table)
            status = "OK" if loaded == expected else "MISMATCH"
        except Exception as exc:
            loaded, status = -1, "FAILED"
            log.error("%s: %s: %s", table, type(exc).__name__, str(exc)[:300])
        rows.append((table, loaded, expected, status, time.time() - started))

    print("\nLoad summary (schema raw)")
    print("-" * 66)
    print(f"{'table':<22}{'rows':>12}{'expected':>12}  {'status':<9}{'secs':>6}")
    for table, loaded, expected, status, secs in rows:
        print(f"{table:<22}{loaded:>12,}{expected:>12,}  {status:<9}{secs:>6.1f}")
    print("-" * 66)
    ok = all(r[3] == "OK" for r in rows)
    print(
        "All tables loaded with expected row counts"
        if ok
        else "Some tables need attention (see above)"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
