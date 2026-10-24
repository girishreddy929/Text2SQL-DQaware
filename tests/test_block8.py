import re

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from src.common.db import get_admin_engine, get_reader_engine
from src.metadata.context import chunk_profiles, column_line, pii_hint
from src.metadata.desc_rank import ranks
from src.metadata.desc_score import band, cosine, partner_indices
from src.metadata.llm_generate import (
    MAX_ATTEMPTS,
    MetadataGenerationError,
    generate_table,
)
from src.metadata.models import (
    ColumnMeta,
    TableMeta,
    check_table_meta,
    clean_column,
    final_pii,
    load_prompt,
)


def prof(name, pos, **kw):
    base = {
        "column_name": name,
        "data_type": "text",
        "type_category": "text",
        "ordinal_position": pos,
        "null_pct": 0,
        "distinct_count": 5,
        "min_value": None,
        "max_value": None,
        "top_values": None,
    }
    return {**base, **kw}


class StubChain:
    def __init__(self, behaviour):
        self.behaviour, self.calls = behaviour, []

    def invoke(self, inputs):
        self.calls.append(inputs)
        return self.behaviour(inputs, len(self.calls))


def names_in(context):
    return re.findall(r'^- "([^"]+)"', context, re.M)


def make_meta(names, desc="d"):
    cols = [
        ColumnMeta(
            column_name=n, description=desc, column_role="category", is_pii=False
        )
        for n in names
    ]
    return TableMeta(table_description="t", table_synonyms=[], columns=cols)


def test_pii_hint():
    assert pii_hint("customer_email") and pii_hint("AdmFName1")
    assert not pii_hint("price")


def test_column_line_quotes_and_top():
    p = prof(
        "Percent (%) Eligible",
        1,
        data_type="numeric",
        type_category="numeric",
        min_value="0",
        max_value="1",
        top_values=[{"value": "x", "count": 3, "pct": 50}],
    )
    line = column_line(p)
    assert (
        line.startswith('"Percent (%) Eligible" numeric')
        and "range 0 .. 1" in line
        and "x (50.0%)" in line
    )


def test_chunk_profiles():
    chunks = chunk_profiles([prof(f"c{i}", i) for i in range(45, 0, -1)])
    assert [len(c) for c in chunks] == [40, 5] and chunks[0][0]["ordinal_position"] == 1


def test_clean_and_check_meta():
    c = ColumnMeta(
        column_name="a",
        description="  x  y ",
        synonyms=["A", "k", "K", ""],
        column_role="flag",
        is_pii=False,
    )
    assert clean_column(c).synonyms == ["k"] and clean_column(c).description == "x y"
    problems = check_table_meta(make_meta(["a", "zz"], desc=" "), ["a", "b"])
    assert "missing column: b" in problems and "unknown column: zz" in problems
    assert "empty description: a" in problems


def test_final_pii():
    assert (
        final_pii("phone_number", False)
        and final_pii("x", True)
        and not final_pii("price", False)
    )


def test_prompt_loads_and_formats():
    assert "demo" in load_prompt().format(source_note="demo")


def test_generate_table_chunks_and_pii():
    profiles = [prof(f"c{i}", i) for i in range(1, 45)] + [prof("customer_email", 45)]
    chain = StubChain(lambda inp, n: make_meta(names_in(inp["context"])))
    meta = generate_table(chain, "note", "s", "t", 10, profiles)
    assert len(chain.calls) == 2 and len(meta.columns) == 45
    assert meta.columns[-1].column_name == "customer_email" and meta.columns[-1].is_pii


def test_generate_table_retries_with_feedback():
    profiles = [prof("a", 1), prof("b", 2)]
    chain = StubChain(lambda inp, n: make_meta(["a"] if n == 1 else ["a", "b"]))
    meta = generate_table(chain, "note", "s", "t", 10, profiles)
    assert len(chain.calls) == 2 and len(meta.columns) == 2
    assert "previous answer had problems" in chain.calls[1]["context"]


@pytest.mark.parametrize("answer", [lambda: make_meta([]), lambda: None])
def test_generate_table_gives_up(answer):
    chain = StubChain(lambda inp, n: answer())
    with pytest.raises(MetadataGenerationError):
        generate_table(chain, "note", "s", "t", 10, [prof("a", 1)])
    assert len(chain.calls) == MAX_ATTEMPTS


def test_cosine_band_partner():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1) and cosine([1, 0], [0, 1]) == 0
    assert cosine([0, 0], [1, 0]) == 0
    assert (band(0.9), band(0.7), band(0.5)) == ("strong", "fair", "weak")
    assert partner_indices(["a", "a", "b", "c", "c", "c"]) == [1, 0, -1, 4, 5, 3]


def test_ranks_including_ties():
    same = [[1, 0], [1, 0]]
    assert ranks(same, same, ["t", "t"]) == [1, 1]  # tie: no disagreement, best rank
    assert ranks([[1, 0], [0, 1]], [[1, 0], [0, 1]], ["t", "t"]) == [1, 1]
    assert ranks([[1, 0], [0, 1]], [[0, 1], [1, 0]], ["t", "t"]) == [2, 2]
    assert ranks([[1, 0]], [[1, 0]], ["t"]) == [None]


@pytest.mark.db
def test_meta_schema_tables():
    with get_admin_engine().connect() as c:
        found = {
            r[0]
            for r in c.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'meta'"
                )
            )
        }
    assert {
        "columns",
        "tables",
        "generation_runs",
        "reference_descriptions",
        "description_scores",
    }.issubset(found)


@pytest.mark.db
def test_reader_cannot_read_meta():
    with get_reader_engine().connect() as c:
        with pytest.raises(DBAPIError):
            c.execute(text("SELECT 1 FROM meta.columns"))


@pytest.mark.db
def test_olist_metadata_complete():
    with get_admin_engine().connect() as c:
        missing = c.execute(
            text(
                "SELECT count(*) FROM dq.latest_profiles p WHERE p.source_id = 'olist' AND NOT EXISTS ("
                "SELECT 1 FROM meta.columns m WHERE m.source_id = p.source_id AND m.schema_name = p.schema_name "
                "AND m.table_name = p.table_name AND m.column_name = p.column_name)"
            )
        ).scalar()
        empty = c.execute(
            text(
                "SELECT count(*) FROM meta.columns WHERE source_id = 'olist' "
                "AND length(trim(description)) = 0"
            )
        ).scalar()
    assert missing == 0 and empty == 0


@pytest.mark.db
def test_bird_reference_loaded():
    with get_admin_engine().connect() as c:
        rows, desc = c.execute(
            text(
                "SELECT count(*), count(description) FROM meta.reference_descriptions "
                "WHERE source_id = 'bird:california_schools'"
            )
        ).one()
    assert (rows, desc) == (89, 72)
