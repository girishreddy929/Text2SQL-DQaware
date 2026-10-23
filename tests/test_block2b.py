"""Block 2B checks: BIRD schemas are loaded as expected. Needs Docker Postgres running."""

from sqlalchemy import text

from src.ingestion.bird_loader import get_admin_engine


def _scalar(sql: str):
    with get_admin_engine().connect() as conn:
        return conn.execute(text(sql)).scalar()


def test_eleven_bird_schemas():
    n = _scalar(
        "select count(*) from information_schema.schemata where schema_name like 'bird\\_%'"
    )
    assert n == 11


def test_seventy_five_bird_tables():
    n = _scalar(
        "select count(*) from information_schema.tables "
        "where table_schema like 'bird\\_%' and table_type = 'BASE TABLE'"
    )
    assert n == 75


def test_public_schema_is_clean():
    n = _scalar(
        "select count(*) from information_schema.tables "
        "where table_schema = 'public' and table_type = 'BASE TABLE'"
    )
    assert n == 0


def test_known_row_counts():
    assert _scalar("select count(*) from bird_superhero.superhero") == 750
    assert _scalar('select count(*) from bird_financial."trans"') == 1056320
