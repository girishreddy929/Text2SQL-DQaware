"""Contract every LLM provider must follow (chat model + embeddings)."""

from abc import ABC, abstractmethod

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel


class LLMProvider(ABC):
    """One subclass per vendor (Gemini, OpenAI, Azure OpenAI, ...)."""

    name: str  # registry key, e.g. "gemini"

    @abstractmethod
    def chat_model(self, temperature: float = 0.0) -> BaseChatModel:
        """Return a LangChain chat model."""

    @abstractmethod
    def embeddings(self) -> Embeddings:
        """Return a LangChain embeddings model."""

    @property
    @abstractmethod
    def chat_model_name(self) -> str:
        """Configured chat model id (for logs and reports)."""

    @property
    @abstractmethod
    def embedding_model_name(self) -> str:
        """Configured embedding model id (for logs and reports)."""
