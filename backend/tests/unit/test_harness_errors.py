"""
Tests for harness error hierarchy.

Verifies:
- All errors are subclasses of HarnessError
- Each error stores the right attributes
- str(exc) contains useful info
- Catch-all via HarnessError works
"""
from __future__ import annotations

import pytest

from dev_guardian.harness.errors import (
    BackendUnavailableError,
    ContextWindowExceededError,
    HarnessError,
    PromptNotFoundError,
    RateLimitError,
    SchemaValidationError,
    SkillNotFoundError,
)


class TestErrorHierarchy:
    def test_all_are_harness_errors(self):
        errors = [
            RateLimitError(wait_seconds=5.0),
            SchemaValidationError("MySchema", "raw", "error detail"),
            PromptNotFoundError("my_prompt"),
            BackendUnavailableError("groq", "connection refused"),
            SkillNotFoundError("my_skill"),
            ContextWindowExceededError(9000, 8000, "groq"),
        ]
        for exc in errors:
            assert isinstance(exc, HarnessError), f"{type(exc)} not a HarnessError"
            assert isinstance(exc, Exception)

    def test_catch_as_harness_error(self):
        with pytest.raises(HarnessError):
            raise RateLimitError(wait_seconds=30.0)

    def test_catch_as_exception(self):
        with pytest.raises(HarnessError):
            raise SkillNotFoundError("missing")


class TestRateLimitError:
    def test_attributes(self):
        exc = RateLimitError(wait_seconds=65.0, backend="anthropic")
        assert exc.wait_seconds == 65.0
        assert exc.backend == "anthropic"

    def test_default_backend(self):
        exc = RateLimitError(wait_seconds=10.0)
        assert exc.backend == "groq"

    def test_str_contains_wait_and_backend(self):
        exc = RateLimitError(wait_seconds=30.0, backend="openai")
        msg = str(exc)
        assert "30.0" in msg
        assert "openai" in msg

    def test_zero_wait(self):
        exc = RateLimitError(wait_seconds=0.0)
        assert exc.wait_seconds == 0.0

    def test_float_precision(self):
        exc = RateLimitError(wait_seconds=65.123)
        assert exc.wait_seconds == 65.123


class TestSchemaValidationError:
    def test_attributes(self):
        exc = SchemaValidationError("GatekeeperReport", '{"bad": true}', "field required")
        assert exc.schema_name == "GatekeeperReport"
        assert exc.raw == '{"bad": true}'
        assert exc.errors == "field required"

    def test_str_contains_schema_name(self):
        exc = SchemaValidationError("MySchema", "raw", "some error")
        assert "MySchema" in str(exc)

    def test_long_errors_truncated_in_message(self):
        long_err = "x" * 500
        exc = SchemaValidationError("S", "r", long_err)
        assert len(str(exc)) < len(long_err) + 100

    def test_errors_fully_stored_as_attribute(self):
        long_err = "e" * 500
        exc = SchemaValidationError("S", "r", long_err)
        assert exc.errors == long_err  # full string, not truncated

    def test_empty_raw(self):
        exc = SchemaValidationError("Schema", "", "error")
        assert exc.raw == ""


class TestPromptNotFoundError:
    def test_attributes(self):
        exc = PromptNotFoundError("gatekeeper.v2")
        assert exc.prompt_id == "gatekeeper.v2"

    def test_str_contains_prompt_id(self):
        exc = PromptNotFoundError("debate")
        assert "debate" in str(exc)


class TestBackendUnavailableError:
    def test_attributes(self):
        exc = BackendUnavailableError("anthropic", "API key missing")
        assert exc.backend == "anthropic"

    def test_str_contains_backend_and_reason(self):
        exc = BackendUnavailableError("groq", "timeout")
        msg = str(exc)
        assert "groq" in msg
        assert "timeout" in msg


class TestSkillNotFoundError:
    def test_attributes(self):
        exc = SkillNotFoundError("nonexistent_skill")
        assert exc.skill_name == "nonexistent_skill"

    def test_str_contains_skill_name(self):
        exc = SkillNotFoundError("debate_mediator")
        assert "debate_mediator" in str(exc)


class TestContextWindowExceededError:
    def test_attributes(self):
        exc = ContextWindowExceededError(tokens=9000, limit=8192, backend="groq")
        assert exc.tokens == 9000
        assert exc.limit == 8192
        assert exc.backend == "groq"

    def test_str_contains_all_info(self):
        exc = ContextWindowExceededError(12000, 8192, "anthropic")
        msg = str(exc)
        assert "12000" in msg
        assert "8192" in msg
        assert "anthropic" in msg

    def test_catch_as_harness_error(self):
        with pytest.raises(HarnessError):
            raise ContextWindowExceededError(1, 0, "groq")
