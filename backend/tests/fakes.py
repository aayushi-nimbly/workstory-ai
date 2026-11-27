"""Test doubles for the model provider."""

import hashlib
import math
import re
from collections.abc import Callable, Sequence
from typing import Any

from app.llm import ChatMessage, ProviderStatus
from app.llm.base import EmbedKind

DIMENSIONS = 768


def _bag_of_words_vector(text: str) -> list[float]:
    """Deterministic embedding: hashed word counts, L2-normalised.

    Texts sharing words get similar vectors, which is enough to test retrieval
    plumbing without a real model.
    """
    vector = [0.0] * DIMENSIONS
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        index = int(hashlib.md5(word.encode()).hexdigest(), 16) % DIMENSIONS
        vector[index] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class FakeLLM:
    def __init__(
        self,
        *,
        reply: str | Callable[[Sequence[ChatMessage]], str] = "",
        status: ProviderStatus | None = None,
    ):
        self.reply = reply
        self._status = status or ProviderStatus(reachable=True)
        self.chat_calls: list[dict[str, Any]] = []
        self.embedded: list[tuple[EmbedKind, str]] = []

    def embed(self, texts: Sequence[str], *, kind: EmbedKind) -> list[list[float]]:
        self.embedded.extend((kind, t) for t in texts)
        return [_bag_of_words_vector(t) for t in texts]

    def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
    ) -> str:
        self.chat_calls.append({"messages": list(messages), "json_schema": json_schema})
        return self.reply(messages) if callable(self.reply) else self.reply

    def status(self) -> ProviderStatus:
        return self._status
