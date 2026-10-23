"""Central configuration. Every other module gets settings from get_settings()."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Reads values from environment variables, then from .env.
    Names are case-insensitive: POSTGRES_HOST in .env -> settings.postgres_host."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )

    # --- Postgres ---
    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_db: str = "trustsql"
    postgres_sslmode: str = "prefer"
    postgres_admin_user: str = "trustsql_admin"
    postgres_admin_password: SecretStr
    t2s_reader_password: SecretStr

    # --- Gemini ---
    google_api_key: SecretStr
    gemini_chat_model: str = "gemini-3.5-flash-lite"
    gemini_embedding_model: str = "gemini-embedding-001"

    # --- Switches (more options get added as we build adapters) ---
    profile: Literal["olist", "bird"] = "olist"
    llm_provider: str = "gemini"
    db_backend: str = "postgres"
    vector_backend: str = "pgvector"

    def _build_url(self, user: str, password: str) -> URL:
        # URL.create escapes special characters safely (never build URLs by string concat).
        return URL.create(
            drivername="postgresql+psycopg",
            username=user,
            password=password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
            query={"sslmode": self.postgres_sslmode},
        )

    @property
    def admin_db_url(self) -> URL:
        return self._build_url(
            self.postgres_admin_user, self.postgres_admin_password.get_secret_value()
        )

    @property
    def reader_db_url(self) -> URL:
        """Read-only role. The role itself is created in Block 2."""
        return self._build_url(
            "t2s_reader", self.t2s_reader_password.get_secret_value()
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
