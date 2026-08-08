"""
OpenAI-wire-compatible backends — Ollama, generic self-hosted engines
(TGI/vLLM/LM Studio), and Hugging Face Inference Providers.

All three speak the OpenAI chat-completions wire format, so they share
one implementation parameterised by base_url / default_model / key
requirements. Install with: pip install "agentic-dev-guardian[openai]"
"""
from __future__ import annotations

import os
import time

from dev_guardian.core.logging import get_logger
from dev_guardian.harness.backends import ChatRequest, ChatResponse
from dev_guardian.harness.errors import BackendUnavailableError, RateLimitError

logger = get_logger(__name__)


class _OpenAICompatibleBackend:
    """Base for providers reachable via the OpenAI chat-completions wire format."""

    name: str = "openai_compatible"
    default_model: str = ""
    context_window: int = 8_000
    key_env_var: str | None = None
    key_required: bool = False
    no_default_model_hint: str = ""

    def __init__(self) -> None:
        try:
            import openai as _openai  # noqa: F401
        except ImportError as exc:
            raise BackendUnavailableError(
                self.name,
                "openai package not installed. Run: pip install 'agentic-dev-guardian[openai]'",
            ) from exc

        import openai

        self._client = openai.OpenAI(
            api_key=self._resolve_api_key(), base_url=self._resolve_base_url()
        )

    def _resolve_base_url(self) -> str:
        raise NotImplementedError

    def _resolve_api_key(self) -> str:
        key = os.environ.get(self.key_env_var, "") if self.key_env_var else ""
        if key:
            return key
        if self.key_required:
            raise BackendUnavailableError(
                self.name, f"{self.key_env_var} is not set"
            )
        return "not-needed"

    def _resolve_model(self, explicit: str | None) -> str:
        if explicit:
            return explicit
        env_model = os.environ.get("GUARDIAN_MODEL", "")
        if env_model:
            return env_model
        if self.default_model:
            return self.default_model
        hint = f" {self.no_default_model_hint}" if self.no_default_model_hint else ""
        raise BackendUnavailableError(
            self.name, f"No model specified. Set GUARDIAN_MODEL.{hint}"
        )

    def complete(self, req: ChatRequest, *, model: str | None = None) -> ChatResponse:
        """Execute a chat completion via the OpenAI-compatible endpoint."""
        import openai

        target_model = self._resolve_model(model)
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
            model=raw.model or target_model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            latency_ms=latency_ms,
        )

    def count_tokens(self, text: str) -> int:
        words = len(text.split())
        return max(1, int(words / 0.75))


class OllamaBackend(_OpenAICompatibleBackend):
    """Local Ollama server — key is a placeholder, never checked by Ollama."""

    name = "ollama"
    default_model = "qwen3:8b"
    context_window = 32_000

    def _resolve_base_url(self) -> str:
        return os.environ.get("GUARDIAN_OLLAMA_BASE_URL", "http://localhost:11434/v1")


class LocalBackend(_OpenAICompatibleBackend):
    """Generic self-hosted OpenAI-compatible engine (TGI, vLLM, LM Studio, ...)."""

    name = "local"
    default_model = ""
    context_window = 8_000
    no_default_model_hint = "Try 'qwen3-8b-instruct' as a starting point."

    def _resolve_base_url(self) -> str:
        base_url = os.environ.get("GUARDIAN_LOCAL_BASE_URL", "")
        if not base_url:
            raise BackendUnavailableError(
                "local",
                "GUARDIAN_LOCAL_BASE_URL is not set. Point it at your self-hosted "
                "OpenAI-compatible endpoint (TGI, vLLM, LM Studio, ...).",
            )
        return base_url


class HuggingFaceBackend(_OpenAICompatibleBackend):
    """Hugging Face Inference Providers router."""

    name = "huggingface"
    default_model = "Qwen/Qwen3-8B-Instruct"
    context_window = 32_000
    key_env_var = "HF_TOKEN"
    key_required = True

    def _resolve_base_url(self) -> str:
        return os.environ.get(
            "GUARDIAN_HF_BASE_URL", "https://router.huggingface.co/v1"
        )
