"""Shapes the metadata LLM must return + pure post-checks. Demo: python -m src.metadata.models"""

import re
from typing import Literal

from pydantic import BaseModel, Field

from config.settings import PROJECT_ROOT

PROMPT_DIR = PROJECT_ROOT / "prompts"
PROMPT_VERSION = "metadata-v1"
MAX_DESC_CHARS = 400
MAX_SYNONYMS = 6
STRONG_PII = re.compile(r"(e?mail|phone|fax|cpf|ssn|passport)", re.I)

ColumnRole = Literal["identifier", "measure", "category", "date", "flag", "free_text"]


class ColumnMeta(BaseModel):
    column_name: str = Field(description="Exact column name as given")
    description: str = Field(description="1-2 sentence business description")
    synonyms: list[str] = Field(
        default_factory=list, description="Up to 6 business terms users may say"
    )
    column_role: ColumnRole
    is_pii: bool = Field(description="True if it identifies or contacts a person")
    pii_reason: str = Field(default="", description="Short reason when is_pii is true")


class TableMeta(BaseModel):
    table_description: str = Field(description="1-2 sentences: what one row represents")
    table_synonyms: list[str] = Field(default_factory=list)
    columns: list[ColumnMeta]


def load_prompt(name: str = "metadata") -> str:
    return (PROMPT_DIR / f"{name}.txt").read_text("utf-8")


def final_pii(column_name: str, llm_flag: bool) -> bool:
    """LLM decision OR an unmistakable name (email, phone, cpf, ssn, passport, fax)."""
    return bool(llm_flag) or bool(STRONG_PII.search(column_name))


def clean_column(c: ColumnMeta) -> ColumnMeta:
    seen, syns = set(), []
    for s in c.synonyms:
        s = s.strip()
        if s and s.lower() not in seen and s.lower() != c.column_name.lower():
            seen.add(s.lower())
            syns.append(s)
    return c.model_copy(
        update={
            "description": " ".join(c.description.split()),
            "synonyms": syns[:MAX_SYNONYMS],
            "pii_reason": c.pii_reason.strip(),
        }
    )


def check_table_meta(
    meta: TableMeta, expected: list[str], need_table_text: bool = True
) -> list[str]:
    """Return a list of problems (empty list = acceptable)."""
    problems = []
    got = [c.column_name for c in meta.columns]
    exp_lower = {e.lower() for e in expected}
    for e in expected:
        if e.lower() not in {g.lower() for g in got}:
            problems.append(f"missing column: {e}")
    for g in got:
        if g.lower() not in exp_lower:
            problems.append(f"unknown column: {g}")
    if len({g.lower() for g in got}) != len(got):
        problems.append("duplicate columns in answer")
    if need_table_text and not meta.table_description.strip():
        problems.append("empty table_description")
    for c in meta.columns:
        if not c.description.strip():
            problems.append(f"empty description: {c.column_name}")
        elif len(c.description) > MAX_DESC_CHARS:
            problems.append(f"description too long: {c.column_name}")
    return problems


def main() -> None:
    col = ColumnMeta(
        column_name="a",
        description=" hi  there ",
        synonyms=["A", "x", "x ", ""],
        column_role="category",
        is_pii=False,
    )
    print(clean_column(col))
    meta = TableMeta(table_description="t", columns=[col])
    print(check_table_meta(meta, ["a", "b"]))
    print(final_pii("customer_email", False), final_pii("price", False))


if __name__ == "__main__":
    main()
