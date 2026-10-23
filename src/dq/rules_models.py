"""Run:  python -m src.dq.rules_models [--check-db]
Block 4, Step 1: the rule vocabulary. Loads config/dq_rules/*.yaml, validates every rule with
Pydantic, prints a summary and shows examples of REJECTED rules. Nothing is executed.
--check-db also verifies that every table/column named in the rules exists in Postgres."""

import argparse
import sys
from collections import Counter
from typing import Annotated, ClassVar, Literal, Union

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)
from sqlalchemy import text

from config.settings import PROJECT_ROOT

RULES_DIR = PROJECT_ROOT / "config" / "dq_rules"

Dimension = Literal[
    "Completeness", "Uniqueness", "Validity", "Consistency", "Timeliness", "Accuracy"
]
# Rule types with an obvious dimension may omit it; the others must say which one.
DEFAULT_DIMENSION = {
    "NON_NULL": "Completeness",
    "UNIQUENESS": "Uniqueness",
    "RANGE": "Validity",
    "SET": "Validity",
    "REGEX": "Validity",
}
FORBIDDEN_IN_SQL = (";", "--", "/*", "*/")


def _clean_sql(value: str) -> str:
    for token in FORBIDDEN_IN_SQL:
        if token in value:
            raise ValueError(f"must not contain {token!r}")
    return value.strip()


class BaseRule(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )  # a typo in a YAML key is an error, not ignored
    needs_column: ClassVar[bool] = False

    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    table: str = Field(pattern=r'^[^."]+\.[^."]+$')  # schema.table
    column: str | None = None
    dimension: Dimension | None = None
    threshold: float = Field(100.0, ge=0, le=100)  # minimum % of rows that must pass
    description: str = ""
    enabled: bool = True
    source_id: str = ""  # filled in by the loader from the YAML file

    @field_validator("column")
    @classmethod
    def _column_plain(cls, v):
        if v is not None and '"' in v:
            raise ValueError("column must not contain a double quote")
        return v

    @model_validator(mode="after")
    def _common_checks(self):
        if self.needs_column and not self.column:
            raise ValueError("this rule type needs 'column'")
        if self.dimension is None:
            default = DEFAULT_DIMENSION.get(getattr(self, "type"))
            if default is None:
                raise ValueError("'dimension' is required for this rule type")
            self.dimension = default
        return self


class NonNullRule(BaseRule):
    needs_column: ClassVar[bool] = True
    type: Literal["NON_NULL"]


class UniquenessRule(BaseRule):
    type: Literal["UNIQUENESS"]
    columns: list[str] | None = None  # composite key; 'column' is shorthand for one

    @model_validator(mode="after")
    def _keys(self):
        if self.columns is None and self.column:
            self.columns = [self.column]
        if not self.columns:
            raise ValueError("UNIQUENESS needs 'column' or 'columns'")
        if any('"' in c for c in self.columns):
            raise ValueError("column names must not contain a double quote")
        return self


class RangeRule(BaseRule):
    needs_column: ClassVar[bool] = True
    type: Literal["RANGE"]
    min_value: float | None = None
    max_value: float | None = None
    strict_min: bool = False  # True means > min_value instead of >=
    strict_max: bool = False
    ignore_null: bool = True  # nulls are not judged here (NON_NULL does that)

    @model_validator(mode="after")
    def _bounds(self):
        if self.min_value is None and self.max_value is None:
            raise ValueError("RANGE needs min_value and/or max_value")
        if (
            None not in (self.min_value, self.max_value)
            and self.min_value > self.max_value
        ):
            raise ValueError("min_value must not be greater than max_value")
        return self


class SetRule(BaseRule):
    needs_column: ClassVar[bool] = True
    type: Literal["SET"]
    values: list[str | int | float] = Field(min_length=1)
    ignore_null: bool = True


class RegexRule(BaseRule):
    needs_column: ClassVar[bool] = True
    type: Literal["REGEX"]
    pattern: str = Field(min_length=1)  # PostgreSQL regular expression (the ~ operator)
    ignore_null: bool = True


class RowConditionRule(BaseRule):
    type: Literal["ROW_CONDITION"]
    expression: str = Field(min_length=1)  # SQL boolean evaluated for every row

    @field_validator("expression")
    @classmethod
    def _safe(cls, v):
        return _clean_sql(v)


class TableConditionRule(BaseRule):
    type: Literal["TABLE_CONDITION"]
    expression: str = Field(min_length=1)  # aggregate boolean, e.g. count(*) >= 90000

    @field_validator("expression")
    @classmethod
    def _safe(cls, v):
        return _clean_sql(v)


class SqlAssertionRule(BaseRule):
    type: Literal["SQL_ASSERTION"]
    sql: str = Field(
        min_length=1
    )  # returns the VIOLATING rows; passes when there are none

    @field_validator("sql")
    @classmethod
    def _select_only(cls, v):
        v = _clean_sql(v)
        if not v.lower().startswith(("select", "with")):
            raise ValueError("must start with SELECT or WITH")
        return v


Rule = Annotated[
    Union[
        NonNullRule,
        UniquenessRule,
        RangeRule,
        SetRule,
        RegexRule,
        RowConditionRule,
        TableConditionRule,
        SqlAssertionRule,
    ],
    Field(discriminator="type"),
]
RULE_ADAPTER = TypeAdapter(Rule)


class RuleFileError(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


def first_error(exc: ValidationError) -> str:
    e = exc.errors()[0]
    where = ".".join(str(p) for p in e["loc"])
    return f"{where}: {e['msg']}" if where else e["msg"]


def load_rules(directory=RULES_DIR) -> list:
    """All rules from every *.yaml in the folder. Raises RuleFileError listing ALL problems."""
    rules: list = []
    problems: list[str] = []
    for path in sorted(directory.glob("*.yaml")):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        source_id, raw_rules = data.get("source_id"), data.get("rules")
        if not source_id or not isinstance(raw_rules, list):
            problems.append(f"{path.name}: needs 'source_id' and a 'rules' list")
            continue
        for i, raw in enumerate(raw_rules, start=1):
            rid = raw.get("id") if isinstance(raw, dict) else "?"
            try:
                rule = RULE_ADAPTER.validate_python(raw)
            except ValidationError as exc:
                problems.append(f"{path.name} rule #{i} ({rid}): {first_error(exc)}")
                continue
            rule.source_id = source_id
            rules.append(rule)
    seen: set[str] = set()
    for r in rules:
        if r.id in seen:
            problems.append(f"duplicate rule id '{r.id}'")
        seen.add(r.id)
    if problems:
        raise RuleFileError(problems)
    return rules


def columns_of(rule) -> list[str]:
    cols = list(getattr(rule, "columns", None) or [])
    if rule.column:
        cols.append(rule.column)
    return sorted(set(cols))


def check_db(rules: list) -> list[str]:
    """Do the tables and columns named in the rules exist? (SQL expressions are not parsed.)"""
    from src.common.db import (
        get_admin_engine,
    )  # lazy: plain validation needs no database

    problems: list[str] = []
    with get_admin_engine().connect() as conn:
        for table in sorted({r.table for r in rules}):
            schema, name = table.split(".")
            have = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = :s AND table_name = :t"
                    ),
                    {"s": schema, "t": name},
                )
            }
            if not have:
                problems.append(f"table {table} does not exist")
                continue
            for r in (x for x in rules if x.table == table):
                problems += [
                    f"{r.id}: column '{c}' not found in {table}"
                    for c in columns_of(r)
                    if c not in have
                ]
    return problems


BAD_EXAMPLES = [
    {
        "id": "bad_range",
        "table": "sales.order_items",
        "column": "price",
        "type": "RANGE",
    },
    {"id": "Bad-ID", "table": "sales.orders", "column": "x", "type": "NON_NULL"},
    {
        "id": "bad_threshold",
        "table": "sales.orders",
        "column": "x",
        "type": "NON_NULL",
        "threshold": 150,
    },
    {
        "id": "bad_injection",
        "table": "sales.orders",
        "type": "ROW_CONDITION",
        "dimension": "Validity",
        "expression": "a > 1; DROP TABLE sales.orders",
    },
    {
        "id": "bad_no_dimension",
        "table": "sales.orders",
        "type": "ROW_CONDITION",
        "expression": "a > 1",
    },
    {"id": "bad_type", "table": "sales.orders", "type": "FUZZY"},
    {
        "id": "bad_typo_key",
        "table": "sales.orders",
        "column": "x",
        "type": "NON_NULL",
        "treshold": 99,
    },
]


def show_rejections() -> None:
    print("\nExamples of REJECTED rules (this is the validation working)")
    for raw in BAD_EXAMPLES:
        try:
            RULE_ADAPTER.validate_python(raw)
            print(f"  {raw['id']:<18} UNEXPECTEDLY ACCEPTED")
        except ValidationError as exc:
            print(f"  {raw['id']:<18} {first_error(exc)[:95]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the DQ rule YAML files.")
    parser.add_argument(
        "--check-db", action="store_true", help="also check tables/columns exist"
    )
    args = parser.parse_args()

    try:
        rules = load_rules()
    except RuleFileError as err:
        print("Rule files have problems:")
        for p in err.problems:
            print("  -", p)
        return 1

    print(f"{'rule id':<34}{'type':<17}{'dimension':<14}{'target':<34}{'min %':>6}")
    print("-" * 105)
    for r in rules:
        target = f"{r.table}.{','.join(columns_of(r))}" if columns_of(r) else r.table
        print(f"{r.id:<34}{r.type:<17}{r.dimension:<14}{target:<34}{r.threshold:>6g}")
    print("-" * 105)
    counts = Counter(r.type for r in rules)
    print(
        f"{len(rules)} rules valid: "
        + ", ".join(f"{t} {n}" for t, n in sorted(counts.items()))
    )
    show_rejections()

    if args.check_db:
        problems = check_db(rules)
        print(
            "\nDatabase check:", "all tables and columns exist" if not problems else ""
        )
        for p in problems:
            print("  -", p)
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
