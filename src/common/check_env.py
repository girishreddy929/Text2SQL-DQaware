"""Run:  python -m src.common.check_env
Prints PASS/FAIL for Settings, Postgres + pgvector, and Gemini. Never prints secrets."""

import sys

from sqlalchemy import text

from config.settings import get_settings
from src.common.db import get_admin_engine
from src.common.llm import get_chat_model, response_text


def _scrub(message: str) -> str:
    """Remove secret values from error messages before printing."""
    try:
        s = get_settings()
        for secret in (
            s.google_api_key,
            s.postgres_admin_password,
            s.t2s_reader_password,
        ):
            value = secret.get_secret_value()
            if value:
                message = message.replace(value, "***")
    except Exception:
        pass
    return message


def check_settings() -> str:
    s = get_settings()
    return (
        f"profile={s.profile}, db={s.postgres_host}:{s.postgres_port}/{s.postgres_db}, "
        f"chat_model={s.gemini_chat_model}"
    )


def check_postgres() -> str:
    with get_admin_engine().connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar_one()
        ext = conn.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one_or_none()
        if ext is None:
            raise RuntimeError(
                "pgvector extension is not installed (see COMMON ERRORS: reset the volume)"
            )
        dist = conn.execute(
            text("SELECT CAST('[1,2,3]' AS vector) <-> CAST('[4,5,6]' AS vector)")
        ).scalar_one()
    return (
        f"{version.split(',')[0]}; pgvector {ext}; distance([1,2,3],[4,5,6])={dist:.4f}"
    )


def check_gemini() -> str:
    llm = get_chat_model()
    reply = response_text(llm.invoke("Reply with exactly one word: hello"))
    if not reply:
        raise RuntimeError("Gemini returned an empty reply")
    return f"model={get_settings().gemini_chat_model} replied {reply[:60]!r}"


def run_check(name: str, fn) -> bool:
    try:
        print(f"[PASS] {name}: {fn()}")
        return True
    except Exception as exc:
        print(f"[FAIL] {name}: {type(exc).__name__}: {_scrub(str(exc))[:400]}")
        return False


def main() -> int:
    print("TrustSQL environment check")
    print("-" * 40)
    if not run_check("Settings", check_settings):
        print(
            "\nFix your .env first (run from the project root; compare with .env.example)."
        )
        return 1
    results = [
        True,
        run_check("Postgres + pgvector", check_postgres),
        run_check("Gemini", check_gemini),
    ]
    passed = sum(results)
    print("-" * 40)
    print(f"{passed}/3 checks passed")
    return 0 if passed == 3 else 1


if __name__ == "__main__":
    sys.exit(main())
