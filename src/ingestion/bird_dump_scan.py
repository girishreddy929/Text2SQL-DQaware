"""Run:  python -m src.ingestion.bird_dump_scan
Block 2B, step 3. READ-ONLY analysis of the BIRD Postgres dump (no DB access).
It streams the 955 MB dump once (about 1-2 minutes) and reports:
  1) statement types in the dump (CREATE/ALTER/SET/...) and OWNER roles
  2) table -> db_id mapping, collisions, unmapped tables
  3) row counts per table: dump COPY rows vs SQLite rows
  4) identifier quoting risk against the PG gold SQL
  5) PK/FK counts (dump vs dev_tables.json)
Writes:
  data/bird/pg_dump_structure.sql  (all non-data statements)
  data/bird/table_db_map.json      (used by the loader in the next step)
Paste the full output back.
"""

import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict

from config.settings import PROJECT_ROOT

BIRD_DIR = PROJECT_ROOT / "data" / "bird"
MINIDEV = BIRD_DIR / "extracted" / "minidev"
MAIN = MINIDEV / "MINIDEV"
DUMP = MINIDEV / "MINIDEV_postgresql" / "BIRD_dev.sql"
TABLES_JSON = MAIN / "dev_tables.json"
PG_QUESTIONS = MAIN / "mini_dev_postgresql.json"
DB_DIR = MAIN / "dev_databases"
OUT_STRUCTURE = BIRD_DIR / "pg_dump_structure.sql"
OUT_MAP = BIRD_DIR / "table_db_map.json"

IDENT = r'(?:"(?:[^"]|"")+"|[A-Za-z_][\w$]*)'
CREATE_RE = re.compile(rf"^CREATE TABLE (?:({IDENT})\.)?({IDENT})")
COPY_RE = re.compile(rf"^COPY (?:({IDENT})\.)?({IDENT})")
COL_RE = re.compile(rf"^({IDENT})\s")
OWNER_RE = re.compile(r"OWNER TO (\S+?);")


def unq(tok):
    if tok is None:
        return None
    if tok.startswith('"'):
        return tok[1:-1].replace('""', '"')
    return tok


def header(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


# ------------------------------------------------------------ dump scan
def scan_dump():
    tables: dict = {}
    kinds: Counter = Counter()
    owners: Counter = Counter()
    structure: list[str] = []
    buf: list[str] = []
    in_copy = None

    with open(DUMP, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if in_copy is not None:
                if line.startswith("\\."):
                    in_copy = None
                else:
                    tables[in_copy]["rows"] += 1
                continue

            s = line.rstrip("\r\n")
            if not buf:
                if not s.strip() or s.startswith("--"):
                    continue
                if s.startswith("\\"):
                    kinds["psql meta: " + s[:25]] += 1
                    structure.append(s)
                    continue
                if s.startswith("COPY "):
                    m = COPY_RE.match(s)
                    key = (unq(m.group(1)) or "(none)", unq(m.group(2)))
                    tables.setdefault(key, {"cols": [], "rows": 0})
                    in_copy = key
                    kinds["COPY (data block)"] += 1
                    continue

            buf.append(s)
            if not s.rstrip().endswith(";"):
                continue

            stmt = "\n".join(buf)
            buf = []
            structure.append(stmt)
            kind = " ".join(stmt.split()[:2]).upper()

            if kind == "ALTER TABLE":
                if "OWNER TO" in stmt:
                    kind += " ... OWNER TO"
                    m = OWNER_RE.search(stmt)
                    if m:
                        owners[m.group(1)] += 1
                elif "FOREIGN KEY" in stmt:
                    kind += " ... FOREIGN KEY"
                elif "PRIMARY KEY" in stmt:
                    kind += " ... PRIMARY KEY"
                else:
                    kind += " ... (other)"
            kinds[kind] += 1

            if stmt.startswith("CREATE TABLE"):
                m = CREATE_RE.match(stmt)
                key = (unq(m.group(1)) or "(none)", unq(m.group(2)))
                info = tables.setdefault(key, {"cols": [], "rows": 0})
                for ln in stmt.split("\n")[1:]:
                    t = ln.strip()
                    if not t or t.startswith(")") or t.upper().startswith("CONSTRAINT"):
                        continue
                    cm = COL_RE.match(t)
                    if cm:
                        info["cols"].append(unq(cm.group(1)))

    OUT_STRUCTURE.write_text("\n\n".join(structure), encoding="utf-8")
    return tables, kinds, owners


def sqlite_counts(db_id: str) -> dict:
    path = DB_DIR / db_id / f"{db_id}.sqlite"
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    out = {}
    names = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    for n in names:
        safe = n.replace('"', '""')
        out[n.lower()] = conn.execute(f'SELECT COUNT(*) FROM "{safe}"').fetchone()[0]
    conn.close()
    return out


def needs_quotes(name: str) -> bool:
    return not re.fullmatch(r"[a-z_][a-z0-9_$]*", name)


# ------------------------------------------------------------ main
def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    for p in (DUMP, TABLES_JSON, PG_QUESTIONS):
        if not p.exists():
            print("Missing file:", p)
            return 1

    print("Scanning dump (streaming ~955 MB, please wait)...")
    tables, kinds, owners = scan_dump()

    header("1) Statement types in the dump")
    for k, v in sorted(kinds.items()):
        print(f"  {v:>6}  {k}")
    print("OWNER roles:", dict(owners) if owners else "(none)")
    print("namespaces used:", dict(Counter(k[0] for k in tables)))
    print(f"structure saved -> {OUT_STRUCTURE.relative_to(PROJECT_ROOT)}")

    # ---- mapping
    dev = json.loads(TABLES_JSON.read_text(encoding="utf-8"))
    dev_tables = {d["db_id"]: d["table_names_original"] for d in dev}
    questions = json.loads(PG_QUESTIONS.read_text(encoding="utf-8"))

    header("2) + 3) Table -> db_id mapping and row counts (dump vs SQLite)")
    sqlite_cache = {db: sqlite_counts(db) for db in dev_tables}
    mapping = []
    problems = 0
    for (schema, name), info in sorted(tables.items(), key=lambda kv: kv[0][1].lower()):
        exact = [d for d, ts in dev_tables.items() if name in ts]
        loose = exact or [
            d for d, ts in dev_tables.items() if name.lower() in [t.lower() for t in ts]
        ]
        db = loose[0] if len(loose) == 1 else None
        status = "OK"
        sq = None
        if len(loose) == 0:
            status = "UNMAPPED"
        elif len(loose) > 1:
            status = f"AMBIGUOUS {loose}"
        else:
            sq = sqlite_cache[db].get(name.lower())
            if sq is None:
                status = "NOT IN SQLITE"
            elif sq != info["rows"]:
                status = "ROW MISMATCH"
        if status != "OK":
            problems += 1
        mapping.append(
            {
                "schema": schema,
                "table": name,
                "db_id": db,
                "columns": info["cols"],
                "dump_rows": info["rows"],
                "sqlite_rows": sq,
                "status": status,
            }
        )

    print(
        f"{'db_id':<25}{'table':<26}{'cols':>5}{'dump_rows':>11}{'sqlite':>11}  status"
    )
    for m in sorted(mapping, key=lambda x: (x["db_id"] or "~", x["table"].lower())):
        print(
            f"{(m['db_id'] or '?'):<25}{m['table']:<26}{len(m['columns']):>5}"
            f"{m['dump_rows']:>11,}{(m['sqlite_rows'] if m['sqlite_rows'] is not None else -1):>11,}  {m['status']}"
        )
    mapped_names = {m["table"].lower() for m in mapping if m["db_id"]}
    missing = [
        (d, t)
        for d, ts in dev_tables.items()
        for t in ts
        if t.lower() not in mapped_names
    ]
    print(f"\ntables in dump: {len(mapping)}   problems: {problems}")
    print("tables in dev_tables.json but missing from dump:", missing or "none")
    print("total dump rows:", f"{sum(m['dump_rows'] for m in mapping):,}")
    OUT_MAP.write_text(
        json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"mapping saved -> {OUT_MAP.relative_to(PROJECT_ROOT)}")

    # ---- quoting risk
    header("4) Identifier quoting risk (names that need double quotes in Postgres)")
    by_db = defaultdict(list)
    for m in mapping:
        if m["db_id"]:
            by_db[m["db_id"]].append(m)
    sqls_by_db = defaultdict(list)
    for q in questions:
        sqls_by_db[q["db_id"]].append(q["SQL"])

    print(
        f"{'db_id':<25}{'names needing quotes':>22}{'gold uses quoted':>18}{'gold uses bare':>16}"
    )
    examples = []
    for db in sorted(by_db):
        names = set()
        for m in by_db[db]:
            names.add(m["table"])
            names.update(m["columns"])
        risky = sorted(n for n in names if needs_quotes(n))
        qh = bh = 0
        for n in risky:
            for sql in sqls_by_db[db]:
                if f'"{n}"' in sql:
                    qh += 1
                elif re.fullmatch(r"\w+", n) and re.search(
                    rf'(?<![\w"]){re.escape(n)}(?![\w"])', sql
                ):
                    bh += 1
        if len(examples) < 12:
            examples += [(db, n) for n in risky[:3]]
        print(f"{db:<25}{len(risky):>22}{qh:>18}{bh:>16}")
    print("\nexamples of names needing quotes:", examples[:12])

    # ---- PK / FK
    header("5) Primary / foreign keys")
    print("dump PK statements:", kinds.get("ALTER TABLE ... PRIMARY KEY", 0))
    print("dump FK statements:", kinds.get("ALTER TABLE ... FOREIGN KEY", 0))
    pk = sum(len(d.get("primary_keys", [])) for d in dev)
    fk = sum(len(d.get("foreign_keys", [])) for d in dev)
    print("dev_tables.json primary-key entries:", pk)
    print("dev_tables.json foreign-key entries:", fk)

    print("\nDone. Paste the full output back.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
