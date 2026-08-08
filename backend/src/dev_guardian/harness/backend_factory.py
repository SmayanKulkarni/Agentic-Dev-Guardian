"""
Backend factory — selects and instantiates the LLM provider.

Selection is explicit via GUARDIAN_PROVIDER, never inferred from which
API keys happen to be set. Defaults to "groq" (today's zero-config
behavior). An unknown provider, or a missing required key for the
selected provider, is a hard failure — no silent fallback.
"""
from __future__ import annotations

import os

from dev_guardian.harness.backends import LLMBackend
from dev_guardian.harness.errors import BackendUnavailableError

_PROVIDERS = ("groq", "anthropic", "openai", "ollama", "local", "huggingface")


def get_backend(name: str | None = None) -> LLMBackend:
    """
    Instantiate the LLM backend selected by `name` or GUARDIAN_PROVIDER.

    Args:
        name: Explicit provider override. Falls back to the
            GUARDIAN_PROVIDER env var, then "groq".

    Returns:
        An instantiated LLMBackend.

    Raises:
        BackendUnavailableError: Unknown provider, or the provider's
            required credentials/dependencies are missing.
    """
    provider = (name or os.environ.get("GUARDIAN_PROVIDER") or "groq").strip().lower()

    if provider not in _PROVIDERS:
        raise BackendUnavailableError(
            provider,
            f"Unknown GUARDIAN_PROVIDER '{provider}'. Choose one of: "
            f"{', '.join(_PROVIDERS)}",
        )

    if provider == "groq":
        from dev_guardian.harness.backends.groq_backend import GroqBackend

        return GroqBackend()
    if provider == "anthropic":
        from dev_guardian.harness.backends.anthropic_backend import AnthropicBackend

        return AnthropicBackend()
    if provider == "openai":
        from dev_guardian.harness.backends.openai_backend import OpenAIBackend

        return OpenAIBackend()
    if provider == "ollama":
        from dev_guardian.harness.backends.openai_compatible import OllamaBackend

        return OllamaBackend()
    if provider == "local":
        from dev_guardian.harness.backends.openai_compatible import LocalBackend

        return LocalBackend()

    from dev_guardian.harness.backends.openai_compatible import HuggingFaceBackend

    return HuggingFaceBackend()
