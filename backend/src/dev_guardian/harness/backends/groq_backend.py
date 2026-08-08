"""
Groq LLM backend — primary provider.

Wraps the existing Groq client with the harness LLMBackend protocol,
preserving Langfuse @observe tracing.  All Groq-specific quirks
(model names, token limit, response format) are contained here.
"""
from __future__ import annotations

import os
import time

from groq import APIStatusError, Groq

from dev_guardian.core.config import get_settings
from dev_guardian.core.logging import get_logger
from dev_guardian.harness.backends import ChatRequest, ChatResponse
from dev_guardian.harness.errors import BackendUnavailableError, RateLimitError

logger = get_logger(__name__)

_WORDS_PER_TOKEN = 0.75  # rough approximation for token counting without tiktoken


class GroqBackend:
    """Groq LLM backend implementing the LLMBackend protocol."""

    name: str = "groq"
    default_model: str = "llama-3.3-70b-versatile"
    context_window: int = 128_000

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.groq_api_key:
            raise BackendUnavailableError("groq", "GROQ_API_KEY is not set")
        self._client = Groq(api_key=settings.groq_api_key)

    def complete(self, req: ChatRequest, *, model: str | None = None) -> ChatResponse:
        """Execute a chat completion via Groq and return a ChatResponse."""
        target_model = model or os.environ.get("GUARDIAN_MODEL") or self.default_model
        t0 = time.monotonic()

        extra: dict = {}
        if req.response_schema is not None:
            extra["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": req.response_schema},
            }

        try:
            raw = self._client.chat.completions.create(
                model=target_model,
                messages=[
                    {"role": "system", "content": req.system},
                    {"role": "user", "content": req.user},
                ],
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                stop=req.stop,
                **extra,
            )
        except APIStatusError as exc:
            if exc.status_code == 429:
                raise RateLimitError(wait_seconds=60.0, backend=self.name) from exc
            raise BackendUnavailableError(self.name, str(exc)) from exc

        latency_ms = int((time.monotonic() - t0) * 1000)
        usage = raw.usage

        return ChatResponse(
            content=raw.choices[0].message.content or "",
            model=raw.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            latency_ms=latency_ms,
        )

    def count_tokens(self, text: str) -> int:
        """Approximate token count (word-based heuristic; no tiktoken dependency)."""
        words = len(text.split())
        return max(1, int(words / _WORDS_PER_TOKEN))
