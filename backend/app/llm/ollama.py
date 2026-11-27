"""LLM provider backed by a local Ollama server."""

import logging
import time
from collections.abc import Sequence
from typing import Any

import httpx

from app.llm.base import ChatMessage, EmbedKind, LLMUnavailableError, ProviderStatus

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 32


class OllamaProvider:
    def __init__(
        self,
        *,
        base_url: str,
        chat_model: str,
        embed_model: str,
        embed_dimensions: int,
        document_prefix: str = "",
        query_prefix: str = "",
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.embed_dimensions = embed_dimensions
        self._prefix = {"document": document_prefix, "query": query_prefix}
        self._client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"Ollama is not reachable: {exc}") from exc
        if response.status_code != 200:
            raise LLMUnavailableError(
                f"Ollama {path} failed ({response.status_code}): {response.text[:300]}"
            )
        return response.json()

    def embed(self, texts: Sequence[str], *, kind: EmbedKind) -> list[list[float]]:
        prefix = self._prefix[kind]
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = [prefix + text for text in texts[start : start + EMBED_BATCH_SIZE]]
            data = self._post("/api/embed", {"model": self.embed_model, "input": batch})
            vectors.extend(data["embeddings"])

        for vector in vectors:
            if len(vector) != self.embed_dimensions:
                raise LLMUnavailableError(
                    f"{self.embed_model} returned {len(vector)} dimensions, "
                    f"expected {self.embed_dimensions} (check EMBED_DIMENSIONS)"
                )
        return vectors

    def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.chat_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature},
        }
        if json_schema is not None:
            payload["format"] = json_schema  # Ollama structured outputs

        started = time.perf_counter()
        data = self._post("/api/chat", payload)
        logger.info(
            "chat model=%s took=%.1fs prompt_tokens=%s output_tokens=%s",
            self.chat_model,
            time.perf_counter() - started,
            data.get("prompt_eval_count"),
            data.get("eval_count"),
        )
        return data["message"]["content"]

    def status(self) -> ProviderStatus:
        try:
            response = self._client.get("/api/tags", timeout=3.0)
            response.raise_for_status()
        except httpx.HTTPError:
            return ProviderStatus(reachable=False)

        installed = {m["name"] for m in response.json().get("models", [])}
        # "nomic-embed-text" is stored as "nomic-embed-text:latest".
        installed |= {name.removesuffix(":latest") for name in installed}
        missing = [m for m in (self.chat_model, self.embed_model) if m not in installed]
        return ProviderStatus(reachable=True, missing_models=missing)
