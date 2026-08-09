"""
Optional Langfuse tracing.

`langfuse` is an extra (`pip install "agentic-dev-guardian[tracing]"`), not a
hard dependency: it expects cloud credentials, and an install that only wants
the MCP server should not be made to carry it. Every module that traces imports
`observe` from here instead of from `langfuse` directly, so a missing package
degrades to a no-op decorator rather than an ImportError at startup.

Supports both call shapes langfuse allows: bare `@observe` and `@observe(...)`.

Langfuse's SDK reads its credentials from `os.environ` directly — it has no
idea `GuardianSettings` or `backend/.env` exist. So before importing it, copy
the resolved settings into the environment (`setdefault`, so a real exported
env var still wins) or a `.env`-only setup silently no-ops every trace with an
auth error nobody sees.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from dev_guardian.core.config import get_settings

_settings = get_settings()
if _settings.langfuse_public_key:
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", _settings.langfuse_public_key)
if _settings.langfuse_secret_key:
    os.environ.setdefault("LANGFUSE_SECRET_KEY", _settings.langfuse_secret_key)
if _settings.langfuse_host:
    os.environ.setdefault("LANGFUSE_HOST", _settings.langfuse_host)

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
