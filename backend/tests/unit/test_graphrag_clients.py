"""
The client cache is the MCP server's hot path: constructing a QdrantCodeClient
loads the fastembed ONNX model, so a tool that builds one per call pays seconds
per request. These tests pin the two properties that matter — the instance is
reused, and an error path can drop it — without needing live services.
"""
from __future__ import annotations

import sys
import types

import pytest

import dev_guardian.graphrag.clients as clients


@pytest.fixture(autouse=True)
def _clean_cache():
    clients.reset_clients()
    yield
    clients.reset_clients()


@pytest.fixture
def counting_clients(monkeypatch):
    """Stub both client modules with constructors that count instantiations.

    Stubbing at the `sys.modules` level rather than patching attributes on
    `clients` is deliberate: the accessors import lazily *inside* the function
    body, so there is no module attribute to patch — and it keeps these tests
    runnable without gqlalchemy, qdrant-client or fastembed present.
    """
    counts = {"memgraph": 0, "retriever": 0}

    class FakeMemgraph:
        def __init__(self) -> None:
            counts["memgraph"] += 1

    class FakeRetriever:
        def __init__(self, memgraph=None, qdrant=None) -> None:
            counts["retriever"] += 1
            self.memgraph = memgraph

    memgraph_module = types.ModuleType("dev_guardian.graphrag.memgraph_client")
    memgraph_module.MemgraphClient = FakeMemgraph
    retriever_module = types.ModuleType("dev_guardian.graphrag.hybrid_retriever")
    retriever_module.HybridRetriever = FakeRetriever

    monkeypatch.setitem(
        sys.modules, "dev_guardian.graphrag.memgraph_client", memgraph_module
    )
    monkeypatch.setitem(
        sys.modules, "dev_guardian.graphrag.hybrid_retriever", retriever_module
    )
    return counts


def test_repeated_calls_reuse_one_instance(counting_clients):
    first = clients.get_retriever()
    second = clients.get_retriever()

    assert first is second
    assert counting_clients["retriever"] == 1


def test_retriever_shares_the_cached_memgraph_client(counting_clients):
    retriever = clients.get_retriever()

    assert retriever.memgraph is clients.get_memgraph()
    assert counting_clients["memgraph"] == 1


def test_reset_forces_a_fresh_connection(counting_clients):
    before = clients.get_retriever()
    clients.reset_clients()
    after = clients.get_retriever()

    assert after is not before
    assert counting_clients["retriever"] == 2
