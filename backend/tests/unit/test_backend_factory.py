"""
Tests for backend_factory.get_backend() provider selection.

No live API calls — each provider class is monkeypatched to a stub
constructor so we only verify dispatch + env var precedence + hard-fail
behavior on bad input.
"""
from __future__ import annotations

import pytest

from dev_guardian.harness.errors import BackendUnavailableError


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("GUARDIAN_PROVIDER", raising=False)


class TestGetBackend:
    def test_defaults_to_groq(self, monkeypatch):
        from dev_guardian.harness import backend_factory

        sentinel = object()
        monkeypatch.setattr(
            "dev_guardian.harness.backends.groq_backend.GroqBackend",
            lambda: sentinel,
        )
        assert backend_factory.get_backend() is sentinel

    def test_explicit_name_overrides_env(self, monkeypatch):
        from dev_guardian.harness import backend_factory

        monkeypatch.setenv("GUARDIAN_PROVIDER", "groq")
        sentinel = object()
        monkeypatch.setattr(
            "dev_guardian.harness.backends.anthropic_backend.AnthropicBackend",
            lambda: sentinel,
        )
        assert backend_factory.get_backend("anthropic") is sentinel

    def test_env_var_selects_provider(self, monkeypatch):
        from dev_guardian.harness import backend_factory

        monkeypatch.setenv("GUARDIAN_PROVIDER", "openai")
        sentinel = object()
        monkeypatch.setattr(
            "dev_guardian.harness.backends.openai_backend.OpenAIBackend",
            lambda: sentinel,
        )
        assert backend_factory.get_backend() is sentinel

    @pytest.mark.parametrize("provider", ["ollama", "local", "huggingface"])
    def test_self_hosted_providers_dispatch(self, monkeypatch, provider):
        from dev_guardian.harness import backend_factory

        sentinel = object()
        cls_name = {
            "ollama": "OllamaBackend",
            "local": "LocalBackend",
            "huggingface": "HuggingFaceBackend",
        }[provider]
        monkeypatch.setattr(
            f"dev_guardian.harness.backends.openai_compatible.{cls_name}",
            lambda: sentinel,
        )
        assert backend_factory.get_backend(provider) is sentinel

    def test_claude_cli_dispatches(self, monkeypatch):
        from dev_guardian.harness import backend_factory

        sentinel = object()
        monkeypatch.setattr(
            "dev_guardian.harness.backends.claude_cli_backend.ClaudeCLIBackend",
            lambda: sentinel,
        )
        assert backend_factory.get_backend("claude_cli") is sentinel

    def test_unknown_provider_raises(self):
        from dev_guardian.harness import backend_factory

        with pytest.raises(BackendUnavailableError):
            backend_factory.get_backend("made-up-provider")

    def test_provider_is_case_and_whitespace_insensitive(self, monkeypatch):
        from dev_guardian.harness import backend_factory

        sentinel = object()
        monkeypatch.setattr(
            "dev_guardian.harness.backends.groq_backend.GroqBackend",
            lambda: sentinel,
        )
        assert backend_factory.get_backend("  GROQ  ") is sentinel


class TestOpenAICompatibleBackend:
    def test_ollama_key_optional_placeholder(self, monkeypatch):
        monkeypatch.delenv("GUARDIAN_OLLAMA_BASE_URL", raising=False)
        from dev_guardian.harness.backends.openai_compatible import OllamaBackend

        backend = OllamaBackend.__new__(OllamaBackend)
        assert backend._resolve_api_key() == "not-needed"
        assert backend._resolve_base_url() == "http://localhost:11434/v1"

    def test_local_requires_base_url(self, monkeypatch):
        monkeypatch.delenv("GUARDIAN_LOCAL_BASE_URL", raising=False)
        from dev_guardian.harness.backends.openai_compatible import LocalBackend

        backend = LocalBackend.__new__(LocalBackend)
        with pytest.raises(BackendUnavailableError):
            backend._resolve_base_url()

    def test_local_has_no_default_model(self, monkeypatch):
        monkeypatch.delenv("GUARDIAN_MODEL", raising=False)
        from dev_guardian.harness.backends.openai_compatible import LocalBackend

        backend = LocalBackend.__new__(LocalBackend)
        with pytest.raises(BackendUnavailableError):
            backend._resolve_model(None)

    def test_huggingface_requires_hf_token(self, monkeypatch):
        monkeypatch.delenv("HF_TOKEN", raising=False)
        from dev_guardian.harness.backends.openai_compatible import HuggingFaceBackend

        backend = HuggingFaceBackend.__new__(HuggingFaceBackend)
        with pytest.raises(BackendUnavailableError):
            backend._resolve_api_key()

    def test_guardian_model_env_overrides_default(self, monkeypatch):
        monkeypatch.setenv("GUARDIAN_MODEL", "custom-model")
        from dev_guardian.harness.backends.openai_compatible import OllamaBackend

        backend = OllamaBackend.__new__(OllamaBackend)
        assert backend._resolve_model(None) == "custom-model"

    def test_explicit_model_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("GUARDIAN_MODEL", "custom-model")
        from dev_guardian.harness.backends.openai_compatible import OllamaBackend

        backend = OllamaBackend.__new__(OllamaBackend)
        assert backend._resolve_model("explicit-model") == "explicit-model"
