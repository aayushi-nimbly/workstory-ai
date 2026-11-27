"""Model provider interface.

The rest of the app only talks to `LLMProvider`, so the local Ollama models can
be swapped for another provider (or a fake in tests) without touching callers.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

EmbedKind = Literal["document", "query"]


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class ProviderStatus:
    reachable: bool
    missing_models: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.reachable and not self.missing_models


class LLMUnavailableError(RuntimeError):
    """The model provider could not be reached or returned an error."""


class LLMProvider(Protocol):
    def embed(self, texts: Sequence[str], *, kind: EmbedKind) -> list[list[float]]:
        """Embed texts. `kind` lets models use different prefixes for documents and queries."""
        ...

    def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
    ) -> str:
        """Return the assistant's reply. With `json_schema`, the reply is JSON matching it."""
        ...

    def status(self) -> ProviderStatus: ...
