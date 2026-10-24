"""Gemini implementation of LLMProvider (the only file that imports langchain_google_genai)."""

import warnings

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from config.settings import Settings, get_settings
from src.adapters.llm.base import LLMProvider

# Hide only this known, harmless warning (the configured model ignores temperature).
warnings.filterwarnings(
    "ignore", message=r".*uses fixed sampling defaults.*", category=UserWarning
)


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, settings: Settings | None = None) -> None:
        self._s = settings or get_settings()

    def chat_model(self, temperature: float = 0.0) -> BaseChatModel:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=self._s.gemini_chat_model,
            google_api_key=self._s.google_api_key.get_secret_value(),
            temperature=temperature,
        )

    def embeddings(self) -> Embeddings:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(
            model=self._s.gemini_embedding_model,
            google_api_key=self._s.google_api_key.get_secret_value(),
        )

    @property
    def chat_model_name(self) -> str:
        return self._s.gemini_chat_model

    @property
    def embedding_model_name(self) -> str:
        return self._s.gemini_embedding_model
