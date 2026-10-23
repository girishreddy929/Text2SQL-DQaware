"""Run:  python -m src.ingestion.bird_loader            (first load)
        python -m src.ingestion.bird_loader --reload   (drop bird_* schemas, load again)

Block 2B, step 4. Restores the BIRD PostgreSQL dump and splits it into one
schema per database (bird_<db_id>). Runs as the ADMIN role, in ONE transaction:
any failure rolls everything back.

Needs: data/bird/table_db_map.json (created by bird_dump_scan) and the dump file.
"""

import argparse
import json
import sys
import time
from collections import defaultdict

from config.settings import PROJECT_ROOT
from src.common import db as dbmod

BIRD_DIR = PROJECT_ROOT / "data" / "bird"
DUMP = BIRD_DIR / "extracted" / "minidev" / "MINIDEV_postgresql" / "BIRD_dev.sql"
MAP_FILE = BIRD_DIR / "table_db_map.json"
READER_ROLE = "t2s_reader"
CHUNK = 5000  # COPY lines per write


def qi(name: str) -> str:
    """Quote an SQL identifier."""
    return '"' + name.replace('"', '""') + '"'


def schema_of(db_id: str) -> str:
    return f"bird_{db_id}"


def get_admin_engine():
    for name in ("get_admin_engine", "admin_engine", "get_engine", "engine"):
        obj = getattr(dbmod, name, None)
        if obj is None:
            continue
        return obj() if callable(obj) else obj
    public = [n for n in dir(dbmod) if not n.startswith("_")]
    raise SystemExit(
        "Could not find the admin engine in src/common/db.py.\n"
        f"Names found: {public}\n"
        "Edit get_admin_engine() in bird_loader.py to use the right one."
    )


def should_skip(stmt: str) -> bool:
    up = stmt.lstrip().upper()
    if up.startswith("ALTER") and "OWNER TO" in up:
        return True
    if up.startswith("SELECT PG_CATALOG.SET_CONFIG"):
        return True
    return False


# ------------------------------------------------------------ steps
def preflight(cur, schemas: list[str], reload: bool) -> None:
    cur.execute("SET statement_timeout = 0")

    cur.execute(
        "SELECT schema_name FROM information_schema.schemata "
        "WHERE schema_name LIKE 'bird\\_%'"
    )
    existing = [r[0] for r in cur.fetchall()]
    if existing and not reload:
        raise SystemExit(
            f"bird_* schemas already exist: {existing}\n"
            "Re-run with --reload to drop and reload them."
        )
    for s in existing:
        print(f"  dropping existing schema {s}")
        cur.execute(f"DROP SCHEMA {qi(s)} CASCADE")

    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
    )
    in_public = [r[0] for r in cur.fetchall()]
    if in_public:
        raise SystemExit(
            f"'public' already contains tables: {in_public}\n"
            "The loader needs an empty public schema. Tell me what these are before continuing."
        )

    for s in schemas:
        cur.execute(f"CREATE SCHEMA {qi(s)}")
    print(f"  created {len(schemas)} schemas")


def restore_dump(cur) -> dict:
    """Stream the dump into public. Returns {table: rows copied}."""
    buf: list[str] = []
    executed = skipped = 0
    copied: dict = {}
    with open(DUMP, "r", encoding="utf-8") as fh:
        for line in fh:
            s = line.rstrip("\r\n")
            if not buf:
                if not s.strip() or s.startswith("--"):
                    continue
                if s.startswith("COPY "):
                    table = s.split()[1]
                    rows = 0
                    chunk: list[str] = []
                    with cur.copy(s) as cp:
                        for data in fh:
                            if data.startswith("\\."):
                                break
                            chunk.append(data)
                            rows += 1
                            if len(chunk) >= CHUNK:
                                cp.write("".join(chunk))
                                chunk = []
                        if chunk:
                            cp.write("".join(chunk))
                    copied[table] = rows
                    print(f"  COPY {table:<45}{rows:>10,} rows")
                    continue
            buf.append(s)
            if s.rstrip().endswith(";"):
                stmt = "\n".join(buf)
                buf = []
                if should_skip(stmt):
                    skipped += 1
                    continue
                cur.execute(stmt)
                executed += 1
    print(f"  statements executed: {executed}, skipped (owner/search_path): {skipped}")
    return copied


def move_tables(cur, mapping: list[dict]) -> None:
    for m in mapping:
        cur.execute(
            f"ALTER TABLE public.{qi(m['table'])} SET SCHEMA {qi(schema_of(m['db_id']))}"
        )
    print(f"  moved {len(mapping)} tables into bird_<db_id> schemas")


def grant_reader(cur, schemas: list[str]) -> None:
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (READER_ROLE,))
    if cur.fetchone() is None:
        print(f"  WARNING: role {READER_ROLE} not found, skipping grants")
        return
    for s in schemas:
        cur.execute(f"GRANT USAGE ON SCHEMA {qi(s)} TO {READER_ROLE}")
        cur.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {qi(s)} TO {READER_ROLE}")
        cur.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {qi(s)} "
            f"GRANT SELECT ON TABLES TO {READER_ROLE}"
        )
    print(f"  granted USAGE + SELECT to {READER_ROLE} on {len(schemas)} schemas")


def verify(cur, mapping: list[dict]) -> None:
    bad = []
    per_db: dict = defaultdict(lambda: [0, 0])
    for m in mapping:
        sch = schema_of(m["db_id"])
        cur.execute(f"SELECT count(*) FROM {qi(sch)}.{qi(m['table'])}")
        n = cur.fetchone()[0]
        per_db[m["db_id"]][0] += 1
        per_db[m["db_id"]][1] += n
        if n != m["dump_rows"] or n != m["sqlite_rows"]:
            bad.append((sch, m["table"], n, m["dump_rows"], m["sqlite_rows"]))
    print(f"\n  {'schema':<32}{'tables':>7}{'rows':>12}")
    for db in sorted(per_db):
        t, r = per_db[db]
        print(f"  {schema_of(db):<32}{t:>7}{r:>12,}")
    total = sum(v[1] for v in per_db.values())
    print(f"  {'TOTAL':<32}{len(mapping):>7}{total:>12,}")

    cur.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
    )
    left = cur.fetchone()[0]
    if bad:
        raise RuntimeError(
            f"Row count mismatches (schema, table, loaded, dump, sqlite): {bad}"
        )
    if left != 0:
        raise RuntimeError(f"{left} tables left behind in public")


# ------------------------------------------------------------ main
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load BIRD Mini-Dev into bird_<db_id> schemas"
    )
    parser.add_argument(
        "--reload", action="store_true", help="drop bird_* schemas first"
    )
    args = parser.parse_args()

    for p in (DUMP, MAP_FILE):
        if not p.exists():
            print("Missing file:", p)
            return 1

    mapping = json.loads(MAP_FILE.read_text(encoding="utf-8"))
    if any(m["status"] != "OK" for m in mapping):
        print(
            "table_db_map.json has problems; re-run bird_dump_scan and fix them first."
        )
        return 1
    schemas = sorted({schema_of(m["db_id"]) for m in mapping})

    engine = get_admin_engine()
    raw = engine.raw_connection()
    conn = raw.driver_connection  # the underlying psycopg 3 connection
    t0 = time.time()
    try:
        with conn.cursor() as cur:
            print("1) pre-flight")
            preflight(cur, schemas, args.reload)
            print("2) restoring dump into public (several minutes)")
            restore_dump(cur)
            print("3) splitting into schemas")
            move_tables(cur, mapping)
            print("4) grants")
            grant_reader(cur, schemas)
            print("5) verifying row counts")
            verify(cur, mapping)
        conn.commit()
        print("\nCOMMITTED.")
    except SystemExit:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        print(
            "\nFAILED, rolled back (nothing was loaded):",
            type(exc).__name__,
            str(exc)[:600],
        )
        return 1
    finally:
        pass

    # ANALYZE outside the transaction so the planner has statistics
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("ANALYZE")
        print("ANALYZE done.")
    finally:
        conn.autocommit = False
        raw.close()

    print(f"Total time: {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
