import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import text

from config.settings import get_settings
from src.common.db import get_admin_engine
from src.common.llm import get_chat_model, response_text


def test_settings_load_and_hide_secrets():
    s = get_settings()
    assert s.profile in ("olist", "bird")
    assert s.postgres_db
    key = s.google_api_key.get_secret_value()
    assert key and key != "your-key-here", "Put your real key in .env"
    assert key not in repr(s)  # SecretStr must hide it


def test_db_urls_hide_password():
    s = get_settings()
    rendered = s.admin_db_url.render_as_string(hide_password=True)
    assert s.postgres_admin_password.get_secret_value() not in rendered
    assert s.admin_db_url.drivername == "postgresql+psycopg"


def test_response_text_handles_str_and_blocks():
    assert response_text(AIMessage(content="  hi  ")) == "hi"
    blocks = [{"type": "text", "text": "hel"}, {"type": "text", "text": "lo"}]
    assert response_text(AIMessage(content=blocks)) == "hello"


@pytest.mark.db
def test_postgres_and_pgvector():
    with get_admin_engine().connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar_one() == 1
        dist = conn.execute(
            text("SELECT CAST('[1,2,3]' AS vector) <-> CAST('[4,5,6]' AS vector)")
        ).scalar_one()
    assert dist == pytest.approx(5.196, abs=1e-3)


@pytest.mark.llm
def test_gemini_replies():
    reply = response_text(get_chat_model().invoke("Reply with exactly one word: hello"))
    assert reply != ""
