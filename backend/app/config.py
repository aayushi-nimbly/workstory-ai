"""Application settings, read from environment variables or `backend/.env`."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://workstory:workstory@localhost:5433/workstory"
    test_database_url: str = (
        "postgresql+psycopg://workstory:workstory@localhost:5433/workstory_test"
    )
    log_level: str = "INFO"

    # Local models served by Ollama (https://ollama.com).
    ollama_url: str = "http://localhost:11434"
    chat_model: str = "llama3.1:8b"
    embed_model: str = "nomic-embed-text"
    embed_dimensions: int = 768
    # nomic-embed-text expects these task prefixes; leave empty for models that don't.
    embed_document_prefix: str = "search_document: "
    embed_query_prefix: str = "search_query: "
    llm_timeout_seconds: float = 120.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
