"""
Process-wide GraphRAG client cache.

Constructing a `QdrantCodeClient` loads the fastembed ONNX embedding model and
runs a probe embedding to discover the vector size — seconds of work. The MCP
server is a long-lived process whose tools were each building a fresh
`HybridRetriever()` per call, paying that cost on every single request.

These accessors keep one instance per process instead. Caching the *client* is
safe even though the stores are embedded and exclusively locked: both clients
open their files per operation and close them again, so a cached instance holds
no lock between calls.

The imports are deferred into the accessors themselves — importing this module
must not drag in kuzu, qdrant-client and fastembed, so the cold start an IDE
spawn measures (ticket 07) never touches them.

Anything needing an isolated or differently-configured client still constructs
`HybridRetriever(...)` / `KuzuClient(...)` directly; these are only the shared
default for long-lived callers, and they resolve their data directory from
$GUARDIAN_REPO (or the process's cwd).
"""
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # imports stay inside the functions — see below
    from dev_guardian.graphrag.hybrid_retriever import HybridRetriever
    from dev_guardian.graphrag.kuzu_client import KuzuClient


@lru_cache(maxsize=1)
def get_kuzu() -> KuzuClient:
    """The shared KuzuClient for this process."""
    from dev_guardian.graphrag.kuzu_client import KuzuClient

    return KuzuClient()


@lru_cache(maxsize=1)
def get_retriever() -> HybridRetriever:
    """The shared HybridRetriever, reusing the cached KuzuClient."""
    from dev_guardian.graphrag.hybrid_retriever import HybridRetriever

    return HybridRetriever(kuzu=get_kuzu())


def reset_clients() -> None:
    """Drop the cached clients so the next call rebuilds them.

    Used after a store error and by tests that swap configuration.
    """
    get_kuzu.cache_clear()
    get_retriever.cache_clear()


__all__ = ["get_kuzu", "get_retriever", "reset_clients"]
