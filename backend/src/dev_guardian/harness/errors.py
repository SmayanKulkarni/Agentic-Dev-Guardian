"""
Harness error hierarchy.

All harness-layer exceptions derive from HarnessError so callers can
catch at any granularity they need.
"""
from __future__ import annotations


class HarnessError(Exception):
    """Base class for all harness errors."""


class RateLimitError(HarnessError):
    """Raised when the TPM budget is exhausted and back-off is required."""

    def __init__(self, wait_seconds: float, backend: str = "groq") -> None:
        self.wait_seconds = wait_seconds
        self.backend = backend
        super().__init__(
            f"Rate limit hit on {backend}. Retry after {wait_seconds:.1f}s."
        )


class SchemaValidationError(HarnessError):
    """Raised when the LLM response fails Pydantic schema validation."""

    def __init__(self, schema_name: str, raw: str, errors: str) -> None:
        self.schema_name = schema_name
        self.raw = raw
        self.errors = errors
        super().__init__(
            f"Schema '{schema_name}' validation failed: {errors[:200]}"
        )


class PromptNotFoundError(HarnessError):
    """Raised when a requested prompt ID is not in the registry."""

    def __init__(self, prompt_id: str) -> None:
        self.prompt_id = prompt_id
        super().__init__(f"Prompt '{prompt_id}' not found in registry.")


class BackendUnavailableError(HarnessError):
    """Raised when no configured backend can serve the request."""

    def __init__(self, backend: str, reason: str) -> None:
        self.backend = backend
        super().__init__(f"Backend '{backend}' unavailable: {reason}")


class SkillNotFoundError(HarnessError):
    """Raised when a requested skill name is not registered."""

    def __init__(self, skill_name: str) -> None:
        self.skill_name = skill_name
        super().__init__(f"Skill '{skill_name}' not registered in SkillRouter.")


class ContextWindowExceededError(HarnessError):
    """Raised when a context cannot fit within the model's context window."""

    def __init__(self, tokens: int, limit: int, backend: str) -> None:
        self.tokens = tokens
        self.limit = limit
        self.backend = backend
        super().__init__(
            f"Context ({tokens} tokens) exceeds {backend} window ({limit} tokens)."
        )
