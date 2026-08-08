"""
Phase 1 — Unit tests for ContextWindowManager chunking.
"""
from __future__ import annotations

import pytest

from dev_guardian.harness.context_window import ContextWindowManager
from dev_guardian.harness.errors import ContextWindowExceededError


class TestContextWindowManager:
    def test_small_context_returns_single_chunk(self):
        mgr = ContextWindowManager(backend_name="groq")
        short = "def foo():\n    pass\n"
        chunks = mgr.fit(short)
        assert len(chunks) == 1
        assert "def foo" in chunks[0]

    def test_large_context_splits_into_multiple_chunks(self):
        # Use reserve_tokens close to the limit so budget is tiny
        mgr = ContextWindowManager(backend_name="groq", reserve_tokens=7900)
        # Create a large fake module — enough to exceed the ~100 token budget
        funcs = "\n".join([f"def func_{i}():\n    pass\n" for i in range(200)])
        chunks = mgr.fit(funcs)
        assert len(chunks) > 1
        # Each chunk should be non-empty
        for c in chunks:
            assert c.strip()

    def test_assert_fits_raises_on_overflow(self):
        mgr = ContextWindowManager(backend_name="groq", reserve_tokens=7000)
        big_text = " ".join(["word"] * 10_000)
        with pytest.raises(ContextWindowExceededError) as exc_info:
            mgr.assert_fits(big_text)
        assert exc_info.value.backend == "groq"

    def test_assert_fits_passes_on_small_text(self):
        mgr = ContextWindowManager(backend_name="groq")
        mgr.assert_fits("short text")  # Should not raise

    def test_different_backends_have_different_budgets(self):
        groq_mgr = ContextWindowManager(backend_name="groq")
        anthropic_mgr = ContextWindowManager(backend_name="anthropic")
        assert anthropic_mgr._token_budget > groq_mgr._token_budget

    def test_line_fallback_split(self):
        mgr = ContextWindowManager(backend_name="groq", reserve_tokens=7500)
        # No function boundaries — should use line-based splitting
        lines = "\n".join([f"x_{i} = {i}" for i in range(3000)])
        chunks = mgr._split_by_lines(lines, budget=100)
        assert len(chunks) > 1


class TestEnvContextOverride:
    """GUARDIAN_CONTEXT_TOKENS wins over both the backend value and the table."""

    def test_env_override_shrinks_budget(self, monkeypatch):
        monkeypatch.setenv("GUARDIAN_CONTEXT_TOKENS", "2000")
        mgr = ContextWindowManager(backend_name="openai", context_window=128_000)
        assert mgr._token_budget == 2000 - mgr.reserve_tokens

    def test_unset_env_falls_back_to_backend_window(self, monkeypatch):
        monkeypatch.delenv("GUARDIAN_CONTEXT_TOKENS", raising=False)
        mgr = ContextWindowManager(backend_name="local", context_window=32_000)
        assert mgr._token_budget == 32_000 - mgr.reserve_tokens

    def test_garbage_env_is_ignored(self, monkeypatch):
        monkeypatch.setenv("GUARDIAN_CONTEXT_TOKENS", "not-a-number")
        mgr = ContextWindowManager(backend_name="groq")
        assert mgr._token_budget == 8_000 - mgr.reserve_tokens
