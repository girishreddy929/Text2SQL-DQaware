"""Run:  python -m src.metadata.ref_loader
Loads BIRD human descriptions (all 11 DBs) into meta.reference_descriptions, one transaction."""

from collections import defaultdict

from sqlalchemy import text

from src.common.db import get_admin_engine
from src.metadata.bird_desc_inspect import BIRD, read_csv

INSERT = text("""
    INSERT INTO meta.reference_descriptions
      (source_id, schema_name, table_name, column_name, human_name, description, data_format, value_description)
    VALUES (:s, :sc, :t, :c, :hn, :d, :df, :vd)""")


def pg_columns(conn) -> dict[str, dict[str, list[str]]]:
    rows = conn.execute(
        text(
            "SELECT table_schema, table_name, column_name FROM information_schema.columns "
            "WHERE left(table_schema, 5) = 'bird_' ORDER BY 1, 2, ordinal_position"
        )
    )
    out: dict = defaultdict(lambda: defaultdict(list))
    for schema, table, col in rows:
        out[schema][table].append(col)
    return out


def build_rows(desc_root, pg) -> tuple[list[dict], list[str]]:
    out, problems = [], []
    for schema, tables in pg.items():
        db_id = schema[len("bird_") :]
        files = {
            p.stem.lower(): p
            for p in (desc_root / db_id / "database_description").glob("*.csv")
        }
        for table, cols in tables.items():
            path = files.get(table.lower())
            if path is None:
                problems.append(f"no CSV for {schema}.{table}")
                continue
            rows, _ = read_csv(path)
            by = {r.get("original_column_name", "").strip().lower(): r for r in rows}
            for col in cols:
                r = by.get(col.strip().lower())
                if r is None:
                    problems.append(f"no CSV row for {schema}.{table}.{col}")
                    continue
                out.append(
                    {
                        "s": f"bird:{db_id}",
                        "sc": schema,
                        "t": table,
                        "c": col,
                        "hn": r.get("column_name") or None,
                        "d": r.get("column_description") or None,
                        "df": r.get("data_format") or None,
                        "vd": r.get("value_description") or None,
                    }
                )
    return out, problems


def main() -> int:
    desc_root = next(BIRD.rglob("dev_databases"))
    engine = get_admin_engine()
    with engine.connect() as conn:
        pg = pg_columns(conn)
    rows, problems = build_rows(desc_root, pg)

    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM meta.reference_descriptions WHERE starts_with(source_id, 'bird:')"
            )
        )
        conn.execute(INSERT, rows)

    expected = defaultdict(lambda: [0, 0])  # source -> [rows, with description]
    for r in rows:
        expected[r["s"]][0] += 1
        expected[r["s"]][1] += 1 if r["d"] else 0
    with engine.connect() as conn:
        stored = {
            s: [n, d]
            for s, n, d in conn.execute(
                text(
                    "SELECT source_id, count(*), count(description) FROM meta.reference_descriptions "
                    "GROUP BY 1 ORDER BY 1"
                )
            )
        }
    bad = 0
    for s in sorted(expected):
        ok = stored.get(s) == expected[s]
        bad += 0 if ok else 1
        print(
            f"  {s:34} rows={expected[s][0]:4} with_description={expected[s][1]:4}  "
            f"{'OK' if ok else 'MISMATCH ' + str(stored.get(s))}"
        )
    tot = [sum(v[i] for v in stored.values()) for i in (0, 1)]
    print(f"TOTAL rows={tot[0]} with_description={tot[1]} | unmatched: {len(problems)}")
    for p in problems[:10]:
        print("  ", p)
    return 0 if not bad and not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
