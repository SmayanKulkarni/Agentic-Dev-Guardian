"""
Shared pytest fixtures for Agentic Dev Guardian test suite.

Provides mock LLM backends and golden-output loaders for tests that
run without live API calls.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOLDEN_DIR = FIXTURES_DIR / "golden"

# ── Canonical test inputs (checked in alongside fixture goldens) ─────────────

TEST_PR_DIFF = (FIXTURES_DIR / "test_pr.diff").read_text() if (FIXTURES_DIR / "test_pr.diff").exists() else (
    "diff --git a/foo.py b/foo.py\n"
    "--- a/foo.py\n+++ b/foo.py\n"
    "@@ -1,3 +1,4 @@\n"
    " def greet(name):\n-    return 'hello'\n"
    "+    return f'hello {name}'\n"
    "+    # added name formatting\n"
)

SAMPLE_GRAPHRAG_CONTEXT = (
    "Function `greet` in foo.py is called by: main, test_greet.\n"
    "No unsafe imports detected.\n"
)


# ── Mock Groq response factory ───────────────────────────────────────────────

def make_groq_response(content: str) -> MagicMock:
    """Build a minimal mock that mimics groq.ChatCompletion response."""
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    resp.model = "llama-3.3-70b-versatile"
    resp.usage.prompt_tokens = 100
    resp.usage.completion_tokens = 50
    return resp


# ── Pytest fixtures ──────────────────────────────────────────────────────────

@pytest.fixture()
def mock_groq_pass():
    """Groq client that always returns a PASS verdict."""
    content = (
        "VERDICT: PASS\n"
        "REASONING: No architectural violations detected in this change.\n"
        "DETAILS: None"
    )
    with patch("groq.Groq") as mock_cls:
        inst = MagicMock()
        inst.chat.completions.create.return_value = make_groq_response(content)
        mock_cls.return_value = inst
        yield inst


@pytest.fixture()
def mock_groq_fail():
    """Groq client that always returns a FAIL verdict."""
    content = (
        "VERDICT: FAIL\n"
        "REASONING: Imported module breaks existing dependency graph.\n"
        "DETAILS:\n- Removed function `auth_check` still called by `middleware.py`"
    )
    with patch("groq.Groq") as mock_cls:
        inst = MagicMock()
        inst.chat.completions.create.return_value = make_groq_response(content)
        mock_cls.return_value = inst
        yield inst


@pytest.fixture()
def mock_groq_warn():
    """Groq client that always returns a WARN verdict."""
    content = (
        "VERDICT: WARN\n"
        "REASONING: Potential type mismatch in return value.\n"
        "DETAILS:\n- `greet` return type changed from str to f-string"
    )
    with patch("groq.Groq") as mock_cls:
        inst = MagicMock()
        inst.chat.completions.create.return_value = make_groq_response(content)
        mock_cls.return_value = inst
        yield inst


@pytest.fixture()
def sample_guardian_state() -> dict[str, Any]:
    """Minimal GuardianState dict for unit tests."""
    return {
        "pr_diff": TEST_PR_DIFF,
        "repo_path": "/tmp/test_repo",
        "user_clearance": 0,
        "graphrag_context": SAMPLE_GRAPHRAG_CONTEXT,
        "messages": [],
    }


@pytest.fixture()
def golden_loader():
    """Helper to load golden JSON fixtures by name."""
    def _load(name: str) -> dict:
        path = GOLDEN_DIR / f"{name}.json"
        if not path.exists():
            pytest.skip(f"Golden fixture '{name}.json' not yet captured.")
        return json.loads(path.read_text())
    return _load


