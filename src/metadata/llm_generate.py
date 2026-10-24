"""One table -> TableMeta via Gemini (chunked, validated, one corrective retry).
No DB access here. `chain` is anything with .invoke(dict) -> TableMeta."""

from typing import Mapping, Sequence

from langchain_core.prompts import ChatPromptTemplate

from src.common.llm_guard import call_resilient
from src.metadata.context import build_table_context, chunk_profiles
from src.metadata.models import (
    ColumnMeta,
    TableMeta,
    check_table_meta,
    clean_column,
    final_pii,
    load_prompt,
)

MAX_ATTEMPTS = 2


class MetadataGenerationError(RuntimeError):
    def __init__(self, table: str, problems: list[str]) -> None:
        super().__init__(f"{table}: {'; '.join(problems[:5])}")
        self.table = table
        self.problems = problems


def build_chain(model):
    prompt = ChatPromptTemplate.from_messages(
        [("system", load_prompt()), ("human", "{context}")]
    )
    return prompt | model.with_structured_output(TableMeta)


def finalize_column(c: ColumnMeta) -> ColumnMeta:
    c = clean_column(c)
    pii = final_pii(c.column_name, c.is_pii)
    reason = c.pii_reason or ("column name suggests personal data" if pii else "")
    return c.model_copy(update={"is_pii": pii, "pii_reason": reason if pii else ""})


def ask_chunk(
    chain,
    source_note: str,
    context: str,
    expected: list[str],
    need_table_text: bool,
    label: str,
) -> TableMeta:
    extra, problems = "", []
    for _ in range(MAX_ATTEMPTS):
        meta = call_resilient(
            chain.invoke, {"source_note": source_note, "context": context + extra}
        )
        problems = (
            ["empty answer"]
            if meta is None
            else check_table_meta(meta, expected, need_table_text)
        )
        if not problems:
            return meta
        extra = "\n\nYour previous answer had problems, fix them: " + "; ".join(
            problems[:8]
        )
    raise MetadataGenerationError(label, problems)


def generate_table(
    chain,
    source_note: str,
    schema: str,
    table: str,
    row_count: int,
    profiles: Sequence[Mapping],
) -> TableMeta:
    chunks = chunk_profiles(profiles)
    table_desc, table_syn, columns = "", [], []
    for i, chunk in enumerate(chunks):
        context = build_table_context(schema, table, row_count, chunk)
        if len(chunks) > 1:
            context += f"\n(Part {i + 1} of {len(chunks)}: describe only the columns listed above.)"
        expected = [p["column_name"] for p in chunk]
        meta = ask_chunk(
            chain, source_note, context, expected, i == 0, f"{schema}.{table}"
        )
        if i == 0:
            table_desc, table_syn = meta.table_description.strip(), meta.table_synonyms
        by_name = {c.column_name.lower(): c for c in meta.columns}
        for name in expected:
            c = by_name[name.lower()].model_copy(update={"column_name": name})
            columns.append(finalize_column(c))
    return TableMeta(
        table_description=table_desc, table_synonyms=table_syn, columns=columns
    )
