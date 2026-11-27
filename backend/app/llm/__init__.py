"""Model providers (chat + embeddings)."""

from functools import lru_cache

from app.config import get_settings
from app.llm.base import ChatMessage, LLMProvider, LLMUnavailableError, ProviderStatus
from app.llm.ollama import OllamaProvider

__all__ = [
    "ChatMessage",
    "LLMProvider",
    "LLMUnavailableError",
    "ProviderStatus",
    "get_llm",
]


@lru_cache
def get_llm() -> LLMProvider:
    """The configured provider. A FastAPI dependency; tests override it with a fake."""
    s = get_settings()
    return OllamaProvider(
        base_url=s.ollama_url,
        chat_model=s.chat_model,
        embed_model=s.embed_model,
        embed_dimensions=s.embed_dimensions,
        document_prefix=s.embed_document_prefix,
        query_prefix=s.embed_query_prefix,
        timeout=s.llm_timeout_seconds,
    )
