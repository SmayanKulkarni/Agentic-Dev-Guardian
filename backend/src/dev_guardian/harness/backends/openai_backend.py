"""
OpenAI LLM backend — fallback provider (stub).

Full implementation; requires OPENAI_API_KEY in env.
Install with: pip install "agentic-dev-guardian[openai]"
"""
from __future__ import annotations

import os
import time

from dev_guardian.core.logging import get_logger
from dev_guardian.harness.backends import ChatRequest, ChatResponse
from dev_guardian.harness.errors import BackendUnavailableError, RateLimitError

logger = get_logger(__name__)


class OpenAIBackend:
    """OpenAI backend implementing the LLMBackend protocol."""

    name: str = "openai"
    default_model: str = "gpt-4o-mini"
    context_window: int = 128_000

    def __init__(self) -> None:
        try:
            import openai as _openai  # noqa: F401
        except ImportError as exc:
            raise BackendUnavailableError(
                "openai",
                "openai package not installed. Run: pip install 'agentic-dev-guardian[openai]'",
            ) from exc

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise BackendUnavailableError("openai", "OPENAI_API_KEY is not set")

        import openai

        self._client = openai.OpenAI(api_key=api_key)

    def complete(self, req: ChatRequest, *, model: str | None = None) -> ChatResponse:
        """Execute a chat completion via OpenAI."""
        import openai

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
                **extra,
            )
        except openai.RateLimitError as exc:
            raise RateLimitError(wait_seconds=60.0, backend=self.name) from exc
        except openai.APIError as exc:
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
        words = len(text.split())
        return max(1, int(words / 0.75))
