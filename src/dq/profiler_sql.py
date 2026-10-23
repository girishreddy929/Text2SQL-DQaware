"""Pure SQL builders and result parsers for the profiler (Block 3, Step 3, Part A).
No database access here, so every statement is easy to read and to unit-test.
Run  python -m src.dq.profiler_sql  to print example SQL (no database needed)."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from config.settings import PROJECT_ROOT

PROFILER_CONFIG_FILE = PROJECT_ROOT / "config" / "profiler.yaml"

NUMERIC = {
    "smallint",
    "integer",
    "bigint",
    "numeric",
    "real",
    "double precision",
    "decimal",
}
TEMPORAL = {
    "date",
    "timestamp without time zone",
    "timestamp with time zone",
    "time without time zone",
    "time with time zone",
}
TEXTUAL = {"text", "character varying", "character"}

Category = Literal["numeric", "text", "temporal", "boolean", "other"]


class ProfilerConfig(BaseModel):
    top_n: int = Field(10, ge=1, le=100)
    value_max_chars: int = Field(100, ge=10, le=1000)
    top_values_categories: list[Category] = ["text", "numeric", "boolean"]
    max_columns_per_query: int = Field(
        50, ge=1, le=100
    )  # 100 cols x 10 exprs < 1664 limit
    statement_timeout_seconds: int = Field(300, ge=1)


def load_profiler_config() -> ProfilerConfig:
    if not PROFILER_CONFIG_FILE.exists():
        return ProfilerConfig()
    with open(PROFILER_CONFIG_FILE, encoding="utf-8") as f:
        return ProfilerConfig.model_validate(yaml.safe_load(f) or {})


def qi(name: str) -> str:
    """Quote an identifier safely (doubles any embedded double quote)."""
    return '"' + name.replace('"', '""') + '"'


def category_of(data_type: str) -> Category:
    t = data_type.lower()
    if t in NUMERIC:
        return "numeric"
    if t in TEXTUAL:
        return "text"
    if t in TEMPORAL:
        return "temporal"
    if t == "boolean":
        return "boolean"
    return "other"


@dataclass(frozen=True)
class ColumnRef:
    name: str
    data_type: str
    position: int  # information_schema ordinal_position; also used to build SQL aliases

    @property
    def category(self) -> Category:
        return category_of(self.data_type)


@dataclass
class ColumnStats:
    name: str
    position: int
    data_type: str
    category: str
    row_count: int
    null_count: int
    null_pct: float
    distinct_count: int | None = None
    distinct_pct: float | None = None  # distinct as % of NON-NULL values
    min_value: str | None = None
    max_value: str | None = None
    mean_value: float | None = None
    stddev_value: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    avg_length: float | None = None
    top_values: list[dict] | None = None
    top_values_sql: str | None = None


def chunk_columns(columns: list[ColumnRef], size: int) -> list[list[ColumnRef]]:
    return [columns[i : i + size] for i in range(0, len(columns), size)]


def build_stats_sql(schema: str, table: str, columns: list[ColumnRef]) -> str:
    """ONE scan of the table computing every statistic for the given columns."""
    parts = ["count(*) AS row_count"]
    for c in columns:
        q, a, cat = qi(c.name), f"c{c.position}", c.category
        parts.append(f"count({q}) AS {a}_nonnull")
        if cat in ("numeric", "text", "temporal", "boolean"):
            parts.append(f"count(DISTINCT {q}) AS {a}_distinct")
        if cat in ("numeric", "text", "temporal"):
            parts.append(f"min({q})::text AS {a}_min")
            parts.append(f"max({q})::text AS {a}_max")
        if cat == "numeric":
            parts.append(f"avg({q})::double precision AS {a}_mean")
            parts.append(f"stddev_samp({q})::double precision AS {a}_std")
        if cat == "text":
            parts.append(f"min(length({q})) AS {a}_minlen")
            parts.append(f"max(length({q})) AS {a}_maxlen")
            parts.append(f"avg(length({q}))::double precision AS {a}_avglen")
    select_list = ",\n  ".join(parts)
    return f"SELECT\n  {select_list}\nFROM {qi(schema)}.{qi(table)}"


def _f(x) -> float | None:
    return None if x is None else round(float(x), 4)


def _i(x) -> int | None:
    return None if x is None else int(x)


def parse_stats(columns: list[ColumnRef], row: Mapping) -> list[ColumnStats]:
    """Turn the single result row of build_stats_sql into one ColumnStats per column."""
    row_count = int(row["row_count"])
    out: list[ColumnStats] = []
    for c in columns:
        a = f"c{c.position}"
        non_null = int(row[f"{a}_nonnull"])
        null_count = row_count - non_null
        distinct = _i(row.get(f"{a}_distinct"))
        out.append(
            ColumnStats(
                name=c.name,
                position=c.position,
                data_type=c.data_type,
                category=c.category,
                row_count=row_count,
                null_count=null_count,
                null_pct=round(null_count * 100.0 / row_count, 4) if row_count else 0.0,
                distinct_count=distinct,
                distinct_pct=(
                    round(distinct * 100.0 / non_null, 4)
                    if distinct is not None and non_null
                    else None
                ),
                min_value=row.get(f"{a}_min"),
                max_value=row.get(f"{a}_max"),
                mean_value=_f(row.get(f"{a}_mean")),
                stddev_value=_f(row.get(f"{a}_std")),
                min_length=_i(row.get(f"{a}_minlen")),
                max_length=_i(row.get(f"{a}_maxlen")),
                avg_length=_f(row.get(f"{a}_avglen")),
            )
        )
    return out


def build_top_values_sql(
    schema: str, table: str, column: str, config: ProfilerConfig
) -> str:
    """Most frequent non-null values of ONE column. Long strings are cut for readability."""
    q = qi(column)
    return (
        f"SELECT left({q}::text, {config.value_max_chars}) AS value, count(*) AS cnt\n"
        f"FROM {qi(schema)}.{qi(table)}\n"
        f"WHERE {q} IS NOT NULL\n"
        f"GROUP BY 1\n"
        f"ORDER BY cnt DESC, value\n"
        f"LIMIT {config.top_n}"
    )


def wants_top_values(stats: ColumnStats, config: ProfilerConfig) -> bool:
    """Skip when the category is switched off, the column is empty, or all values are unique
    (a top-10 list of unique IDs tells us nothing)."""
    if stats.category not in config.top_values_categories:
        return False
    non_null = stats.row_count - stats.null_count
    if non_null == 0 or stats.distinct_count is None:
        return False
    return stats.distinct_count < non_null


def format_top_values(rows: list[tuple], row_count: int) -> list[dict]:
    """[(value, count), ...] -> JSON-ready list; pct is the % of ALL rows."""
    return [
        {
            "value": value,
            "count": int(n),
            "pct": round(int(n) * 100.0 / row_count, 4) if row_count else 0.0,
        }
        for value, n in rows
    ]


def main() -> None:
    """Demo with made-up numbers: shows the generated SQL and the parsing, no database."""
    cfg = ProfilerConfig()
    cols = [
        ColumnRef("order_id", "text", 1),
        ColumnRef("order_status", "text", 3),
        ColumnRef("order_delivered_customer_date", "timestamp without time zone", 7),
    ]
    print(
        "chunk sizes when splitting 3 columns into chunks of 2:",
        [len(c) for c in chunk_columns(cols, 2)],
    )
    print("\n-- STATS SQL (one scan)\n" + build_stats_sql("sales", "orders", cols))
    print(
        "\n-- TOP VALUES SQL\n"
        + build_top_values_sql("sales", "orders", "order_status", cfg)
    )

    fake_row = {
        "row_count": 99441,
        "c1_nonnull": 99441,
        "c1_distinct": 99441,
        "c1_min": "00010242fe8c5a6d",
        "c1_max": "fffe41c64501cc87",
        "c1_minlen": 32,
        "c1_maxlen": 32,
        "c1_avglen": 32.0,
        "c3_nonnull": 99441,
        "c3_distinct": 8,
        "c3_min": "approved",
        "c3_max": "unavailable",
        "c3_minlen": 7,
        "c3_maxlen": 11,
        "c3_avglen": 8.5,
        "c7_nonnull": 96476,
        "c7_distinct": 95664,
        "c7_min": "2016-10-11 13:46:32",
        "c7_max": "2018-10-17 13:22:46",
    }
    print("\n-- PARSED (made-up numbers)")
    for s in parse_stats(cols, fake_row):
        print(
            f"{s.name:<32} null_pct={s.null_pct:<8} distinct_pct={s.distinct_pct:<9} "
            f"top_values={wants_top_values(s, cfg)}"
        )
    print("\n-- FORMATTED TOP VALUES")
    print(format_top_values([("delivered", 96478), ("shipped", 1107)], 99441))


if __name__ == "__main__":
    main()
