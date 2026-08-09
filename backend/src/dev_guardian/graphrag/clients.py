"""
Process-wide GraphRAG client cache.

Constructing a `QdrantCodeClient` loads the fastembed ONNX embedding model and
runs a probe embedding to discover the vector size — seconds of work. The MCP
server is a long-lived process whose tools were each building a fresh
`HybridRetriever()` per call, paying that cost on every single request.

These accessors keep one instance per process instead. The imports are deferred into the accessors themselves — importing this module
must not drag in gqlalchemy, qdrant-client and fastembed, so the cold start an
IDE spawn measures (ticket 07) never touches them.

Anything needing an isolated or differently-configured client still constructs
`HybridRetriever(...)` / `MemgraphClient()` directly; these are only the shared
default for long-lived callers.
"""
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # imports stay inside the functions — see below
    from dev_guardian.graphrag.hybrid_retriever import HybridRetriever
    from dev_guardian.graphrag.memgraph_client import MemgraphClient


@lru_cache(maxsize=1)
def get_memgraph() -> MemgraphClient:
    """The shared MemgraphClient for this process."""
    from dev_guardian.graphrag.memgraph_client import MemgraphClient

    return MemgraphClient()


@lru_cache(maxsize=1)
def get_retriever() -> HybridRetriever:
    """The shared HybridRetriever, reusing the cached MemgraphClient."""
    from dev_guardian.graphrag.hybrid_retriever import HybridRetriever

    return HybridRetriever(memgraph=get_memgraph())


def reset_clients() -> None:
    """Drop the cached clients so the next call reconnects.

    Used after a connection error and by tests that swap configuration.
    """
    get_memgraph.cache_clear()
    get_retriever.cache_clear()


__all__ = ["get_memgraph", "get_retriever", "reset_clients"]
