"""
QdrantCodeClient against real embedded Qdrant in tmp_path — no server.

`fastembed`'s real model is a ~270MB download, so the embedder is stubbed with
a deterministic tiny vector. What is under test is the storage mode, the ABAC
payload filter and the lock lifecycle, none of which depend on real embeddings.
"""
from __future__ import annotations

import pytest

from dev_guardian.parsers.models import ASTNode, NodeType


class FakeEmbedder:
    """Deterministic 4-d embeddings: one axis per distinct text."""

    def __init__(self, *_args, **_kwargs) -> None:
        self._seen: dict[str, int] = {}

    def embed(self, texts):
        import numpy as np

        for text in texts:
            idx = self._seen.setdefault(text, len(self._seen) % 4)
            vec = np.zeros(4, dtype="float32")
            vec[idx] = 1.0
            yield vec


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import dev_guardian.graphrag.qdrant_client as module

    monkeypatch.setattr(module, "TextEmbedding", FakeEmbedder)
    return module.QdrantCodeClient(data_dir=tmp_path)


def _node(name: str, clearance: int = 0) -> ASTNode:
    return ASTNode(
        name=name,
        node_type=NodeType.FUNCTION,
        file_path="/repo/app.py",
        start_line=1,
        end_line=4,
        docstring=f"docs for {name}",
        owner_team="core",
        clearance_level=clearance,
    )


def test_storage_lives_under_the_repo_data_dir(client, tmp_path):
    client.ensure_collection()

    assert client.data_dir == tmp_path / ".guardian" / "qdrant"
    assert client.data_dir.exists()


def test_ingest_returns_point_count(client):
    client.ensure_collection()

    assert client.ingest_nodes([_node("alpha"), _node("beta")]) == 2


def test_search_finds_an_ingested_node(client):
    client.ensure_collection()
    client.ingest_nodes([_node("calculate_tax")])

    hits = client.semantic_search("calculate_tax", user_clearance=0, top_k=5)

    assert [h["name"] for h in hits] == ["calculate_tax"]


def test_search_excludes_over_clearance_nodes(client):
    client.ensure_collection()
    client.ingest_nodes([_node("secret_job", clearance=5)])

    assert client.semantic_search("secret_job", user_clearance=0) == []
    assert len(client.semantic_search("secret_job", user_clearance=5)) == 1


def test_clear_collection_empties_the_store(client):
    client.ensure_collection()
    client.ingest_nodes([_node("alpha")])

    client.clear_collection()

    assert client.semantic_search("alpha", user_clearance=0) == []


def test_lock_is_released_between_operations(client, tmp_path, monkeypatch):
    """A second client on the same directory must be able to open it."""
    import dev_guardian.graphrag.qdrant_client as module

    client.ensure_collection()
    client.ingest_nodes([_node("alpha")])

    monkeypatch.setattr(module, "TextEmbedding", FakeEmbedder)
    second = module.QdrantCodeClient(data_dir=tmp_path)

    assert len(second.semantic_search("alpha", user_clearance=0)) == 1


def test_nested_sessions_reuse_one_client(client):
    with client.session() as outer:
        with client.session() as inner:
            assert inner is outer
