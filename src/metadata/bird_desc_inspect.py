"""Read-only. Run:  python -m src.metadata.bird_desc_inspect
Checks BIRD description CSVs against dev_tables.json (names, empties, encoding)."""

import csv
import json

from config.settings import PROJECT_ROOT

BIRD = PROJECT_ROOT / "data" / "bird"


def read_csv(path) -> tuple[list[dict], str]:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(path, newline="", encoding=enc) as f:
                rows = list(csv.DictReader(f))
            break
        except UnicodeDecodeError:
            continue
    clean = [
        {
            k.strip().lower(): (v or "").strip()
            for k, v in r.items()
            if k and isinstance(v, (str, type(None)))
        }
        for r in rows
    ]
    return clean, enc


def main() -> None:
    tables_file = next(BIRD.rglob("dev_tables.json"))
    desc_root = next(BIRD.rglob("dev_databases"))
    print("dev_tables.json :", tables_file)
    print("dev_databases   :", desc_root, "\n")
    dbs = json.loads(tables_file.read_text("utf-8"))
    tot = {"cols": 0, "matched": 0, "desc": 0, "value": 0}

    for db in sorted(dbs, key=lambda d: d["db_id"]):
        db_id = db["db_id"]
        files = {
            p.stem.lower(): p
            for p in (desc_root / db_id / "database_description").glob("*.csv")
        }
        for ti, table in enumerate(db["table_names_original"]):
            cols = [
                c.strip().lower() for t, c in db["column_names_original"] if t == ti
            ]
            path = files.get(table.lower())
            if path is None:
                print(f"{db_id}.{table}: NO CSV FOUND")
                continue
            rows, enc = read_csv(path)
            names = {r.get("original_column_name", "").lower() for r in rows}
            miss = [c for c in cols if c not in names]
            extra = sorted(n for n in names if n and n not in cols)
            d = sum(1 for r in rows if r.get("column_description"))
            v = sum(1 for r in rows if r.get("value_description"))
            tot["cols"] += len(cols)
            tot["matched"] += len(cols) - len(miss)
            tot["desc"] += d
            tot["value"] += v
            flag = "" if not miss and not extra else f" | missing={miss} extra={extra}"
            print(
                f"{db_id}.{table}: cols={len(cols)} csv_rows={len(rows)} "
                f"desc={d} value_desc={v} enc={enc}{flag}"
            )

    print("\nTOTAL", tot)
    sample = next(iter(files.values()))
    rows, _ = read_csv(sample)
    print(f"\nSample ({sample.name}), header keys: {list(rows[0])}")
    for r in rows[:3]:
        print(" ", r)


if __name__ == "__main__":
    main()
