"""LLM factory. The rest of the project calls get_chat_model() / get_embeddings()
and never names a provider. To add a vendor: write src/adapters/llm/<vendor>.py
(subclass LLMProvider) and add ONE line to PROVIDERS."""

from importlib import import_module

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel

from config.settings import get_settings
from src.adapters.llm.base import LLMProvider

# provider name -> (module, class). Imported lazily, so unused vendors cost nothing.
PROVIDERS: dict[str, tuple[str, str]] = {
    "gemini": ("src.adapters.llm.gemini", "GeminiProvider"),
}


def get_provider(name: str | None = None) -> LLMProvider:
    key = (name or get_settings().llm_provider).lower()
    if key not in PROVIDERS:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{key}'. Supported: {', '.join(sorted(PROVIDERS))}"
        )
    module, cls = PROVIDERS[key]
    return getattr(import_module(module), cls)()


def get_chat_model(temperature: float = 0.0) -> BaseChatModel:
    return get_provider().chat_model(temperature)


def get_embeddings() -> Embeddings:
    return get_provider().embeddings()


def response_text(response) -> str:
    """Return plain text from a model reply.
    Depending on version/model, .content is a str OR a list of content blocks."""
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content.strip()
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts).strip()
