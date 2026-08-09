"""
Provider-agnostic LLM backend protocol.

Every backend (Groq, Anthropic, OpenAI) implements LLMBackend so the
rest of the harness stays entirely provider-agnostic.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Normalised request handed to any LLMBackend."""

    system: str
    user: str
    temperature: float = 0.1
    max_tokens: int = 1024
    stop: list[str] | None = None
    response_schema: dict | None = None


class ChatResponse(BaseModel):
    """Normalised response returned from any LLMBackend."""

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


@runtime_checkable
class LLMBackend(Protocol):
    """Contract every provider adapter must satisfy."""

    name: str
    default_model: str
    context_window: int

    def complete(self, req: ChatRequest, *, model: str | None = None) -> ChatResponse:
        """Execute a chat completion and return a normalised ChatResponse."""
        ...

    def count_tokens(self, text: str) -> int:
        """Approximate token count for the given text using this backend's tokenizer."""
        ...
