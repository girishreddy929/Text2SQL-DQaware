"""LLM factory. The rest of the project calls get_chat_model() and never names a provider."""

from langchain_core.language_models.chat_models import BaseChatModel

from config.settings import get_settings


def get_chat_model(temperature: float = 0.0) -> BaseChatModel:
    settings = get_settings()
    provider = settings.llm_provider.lower()

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.gemini_chat_model,
            google_api_key=settings.google_api_key.get_secret_value(),
            temperature=temperature,
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER '{settings.llm_provider}'. Supported: gemini"
    )


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
