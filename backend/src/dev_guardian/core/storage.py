"""
Where Guardian's embedded stores live, and what "the store is busy" means.

Both backing stores are embedded and file-based: Kùzu under
``<repo>/.guardian/kuzu`` and Qdrant under ``<repo>/.guardian/qdrant``. The
directory is per indexed repository, matching the existing rule that the
indexed repo is a per-invocation argument and never global configuration.

Both engines take an exclusive cross-process lock on their directory, so two
Guardian processes pointed at one repo collide. That is a normal thing for a
user to do (an IDE holds an MCP server open while they run `dev-guardian
index` in a terminal), so the collision gets a real error message rather than
a raw `RuntimeError` from a vendored engine.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

GUARDIAN_DIR_NAME = ".guardian"

# Substrings that identify a lock collision in each engine's error text.
_BUSY_MARKERS = (
    "could not set lock on file",           # kuzu
    "already accessed by another instance",  # qdrant local mode
)


class StoreBusyError(RuntimeError):
    """Another process holds the embedded store's lock. Message is user-facing."""

    def __init__(self, path: str, cause: Exception) -> None:
        super().__init__(
            f"Guardian's local store at {path} is held by another process.\n"
            "The embedded Kùzu and Qdrant stores allow one process at a time. "
            "The usual cause is an IDE-spawned `dev-guardian serve` holding the "
            "same repository open — close that Guardian connection (or stop the "
            "other run) and retry.\n"
            f"Underlying error: {cause}"
        )


@contextmanager
def busy_store(path: str) -> Iterator[None]:
    """Translate an engine lock error into StoreBusyError; pass everything else."""
    try:
        yield
    except RuntimeError as exc:
        if any(marker in str(exc).lower() for marker in _BUSY_MARKERS):
            raise StoreBusyError(path, exc) from exc
        raise


def guardian_data_dir(repo: Path | str | None = None) -> Path:
    """The `.guardian` directory for `repo`, created if missing.

    Resolution order: the explicit argument, then ``$GUARDIAN_REPO`` (which is
    how an IDE's MCP `env` block names the repo it opened Guardian against),
    then the current working directory.
    """
    root = repo if repo is not None else os.environ.get("GUARDIAN_REPO") or Path.cwd()
    data_dir = Path(root).expanduser().resolve() / GUARDIAN_DIR_NAME
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
