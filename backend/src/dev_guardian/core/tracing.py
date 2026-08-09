"""
Optional Langfuse tracing.

`langfuse` is an extra (`pip install "agentic-dev-guardian[tracing]"`), not a
hard dependency: it expects cloud credentials, and an install that only wants
the MCP server should not be made to carry it. Every module that traces imports
`observe` from here instead of from `langfuse` directly, so a missing package
degrades to a no-op decorator rather than an ImportError at startup.

Supports both call shapes langfuse allows: bare `@observe` and `@observe(...)`.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:  # pragma: no cover - exercised by whichever install shape is present
    from langfuse import observe

    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False

    def observe(*args: Any, **kwargs: Any) -> Any:  # type: ignore[misc]
        """No-op stand-in for `langfuse.observe` when langfuse isn't installed."""
        if len(args) == 1 and not kwargs and callable(args[0]):
            return args[0]  # bare @observe

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return fn

        return decorator


__all__ = ["LANGFUSE_AVAILABLE", "observe"]
