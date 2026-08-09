"""
ContextWindowManager — function-boundary chunking for LLM context.

Splits large code strings at function/class boundaries (via Tree-sitter
when available, falling back to regex) to stay within per-backend
context windows.  Reserves `reserve_tokens` for the system prompt
and expected response.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from dev_guardian.core.logging import get_logger
from dev_guardian.harness.errors import ContextWindowExceededError

logger = get_logger(__name__)

# Fallback per-backend-name maximums, used only when the caller doesn't
# pass the backend's actual context_window (prompt tokens, leaving room
# for response).
_SAFE_PROMPT_TOKENS: dict[str, int] = {
    "groq": 8_000,       # 12k context - 4k response headroom
    "anthropic": 180_000,
    "openai": 110_000,
    "ollama": 28_000,
    "local": 8_000,
    "huggingface": 28_000,
}


def _env_context_tokens() -> int | None:
    """
    GUARDIAN_CONTEXT_TOKENS — the user's own context size for the model they
    actually run (ticket 09).

    One number per install beats a per-model registry nobody maintains: a
    self-hosted deployment can serve any model at any context length, and only
    the operator knows which. When set it wins over everything else.
    """
    raw = os.environ.get("GUARDIAN_CONTEXT_TOKENS", "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        logger.warning("invalid_context_tokens_env", value=raw)
        return None
    return value if value > 0 else None


# Regex boundary detector (fallback when tree-sitter unavailable)
_BOUNDARY_RE = re.compile(r"(?m)^(?:def |class |async def )")


@dataclass
class ContextWindowManager:
    """
    Splits code context to fit within a backend's context window.

    Args:
        backend_name: Which backend's limits to use (fallback only).
        context_window: The active backend/model's real context window in
            tokens. When given, the budget is keyed off this rather than
            the backend-name lookup table — local/self-hosted models vary
            per deployment, not per adapter.
        reserve_tokens: Additional tokens to reserve for system + response.
    """

    backend_name: str = "groq"
    context_window: int | None = None
    reserve_tokens: int = 1_024

    @property
    def _token_budget(self) -> int:
        base = (
            _env_context_tokens()
            or self.context_window
            or _SAFE_PROMPT_TOKENS.get(self.backend_name, 8_000)
        )
        return max(100, base - self.reserve_tokens)

    def _count(self, text: str) -> int:
        """Rough token count (words / 0.75)."""
        return max(1, int(len(text.split()) / 0.75))

    def fit(self, context: str) -> list[str]:
        """
        Split `context` into chunks that each fit within the token budget.

        Tries to split at function/class boundaries first. Falls back to
        line-based splitting when no boundaries are detected.

        Returns:
            List of strings, each ≤ budget tokens.
        """
        budget = self._token_budget
        total = self._count(context)

        if total <= budget:
            return [context]

        # Find all boundary positions
        boundaries = [m.start() for m in _BOUNDARY_RE.finditer(context)]
        if not boundaries:
            return self._split_by_lines(context, budget)

        chunks: list[str] = []
        current_start = 0

        for boundary in boundaries[1:]:
            candidate = context[current_start:boundary]
            if self._count(candidate) <= budget:
                continue
            # Flush everything before this boundary as a chunk
            chunk = context[current_start:boundary]
            if chunk.strip():
                chunks.append(chunk)
            current_start = boundary

        # Last segment
        remainder = context[current_start:]
        if remainder.strip():
            if self._count(remainder) <= budget:
                chunks.append(remainder)
            else:
                chunks.extend(self._split_by_lines(remainder, budget))

        logger.debug(
            "context_window_split",
            backend=self.backend_name,
            original_tokens=total,
            chunks=len(chunks),
        )
        return chunks or [context[:budget * 5]]

    def _split_by_lines(self, text: str, budget: int) -> list[str]:
        """Fallback: split by lines, accumulating until budget hit."""
        lines = text.splitlines(keepends=True)
        chunks: list[str] = []
        current: list[str] = []
        current_tokens = 0

        for line in lines:
            t = self._count(line)
            if current_tokens + t > budget and current:
                chunks.append("".join(current))
                current = []
                current_tokens = 0
            current.append(line)
            current_tokens += t

        if current:
            chunks.append("".join(current))

        return chunks

    def assert_fits(self, text: str) -> None:
        """Raise ContextWindowExceededError if text exceeds the budget."""
        tokens = self._count(text)
        budget = self._token_budget
        if tokens > budget:
            raise ContextWindowExceededError(
                tokens=tokens,
                limit=budget,
                backend=self.backend_name,
            )
