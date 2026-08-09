"""
Anthropic LLM backend — fallback provider.

Full implementation; requires ANTHROPIC_API_KEY in env.
Install with: pip install "agentic-dev-guardian[anthropic]"
"""
from __future__ import annotations

import json
import os
import time

from dev_guardian.core.logging import get_logger
from dev_guardian.harness.backends import ChatRequest, ChatResponse
from dev_guardian.harness.errors import BackendUnavailableError, RateLimitError

logger = get_logger(__name__)

_STRUCTURED_TOOL_NAME = "emit_result"


class AnthropicBackend:
    """Anthropic Claude backend implementing the LLMBackend protocol."""

    name: str = "anthropic"
    default_model: str = "claude-3-5-haiku-20241022"
    context_window: int = 200_000

    def __init__(self) -> None:
        try:
            import anthropic as _anthropic  # noqa: F401
        except ImportError as exc:
            raise BackendUnavailableError(
                "anthropic",
                "anthropic package not installed. Run: pip install 'agentic-dev-guardian[anthropic]'",
            ) from exc

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise BackendUnavailableError("anthropic", "ANTHROPIC_API_KEY is not set")

        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, req: ChatRequest, *, model: str | None = None) -> ChatResponse:
        """
        Execute a completion via Anthropic Messages API.

        Anthropic has no native json_schema response mode. When
        req.response_schema is set, structured output is emulated by
        defining a single tool matching the schema and forcing the model
        to call it — the tool-call arguments become the JSON result.
        """
        import anthropic

        target_model = model or os.environ.get("GUARDIAN_MODEL") or self.default_model
        t0 = time.monotonic()

        extra: dict = {}
        if req.response_schema is not None:
            extra["tools"] = [
                {
                    "name": _STRUCTURED_TOOL_NAME,
                    "description": "Emit the structured result.",
                    "input_schema": req.response_schema,
                }
            ]
            extra["tool_choice"] = {"type": "tool", "name": _STRUCTURED_TOOL_NAME}

        try:
            raw = self._client.messages.create(
                model=target_model,
                max_tokens=req.max_tokens,
                system=req.system,
                messages=[{"role": "user", "content": req.user}],
                temperature=req.temperature,
                **extra,
            )
        except anthropic.RateLimitError as exc:
            raise RateLimitError(wait_seconds=60.0, backend=self.name) from exc
        except anthropic.APIError as exc:
            raise BackendUnavailableError(self.name, str(exc)) from exc

        latency_ms = int((time.monotonic() - t0) * 1000)
        if req.response_schema is not None:
            tool_use = next(
                (block for block in raw.content if block.type == "tool_use"), None
            )
            content = json.dumps(tool_use.input) if tool_use else ""
        else:
            content = raw.content[0].text if raw.content else ""

        return ChatResponse(
            content=content,
            model=raw.model,
            prompt_tokens=raw.usage.input_tokens,
            completion_tokens=raw.usage.output_tokens,
            latency_ms=latency_ms,
        )

    def count_tokens(self, text: str) -> int:
        words = len(text.split())
        return max(1, int(words / 0.75))
