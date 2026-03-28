"""
Qdrant Vector Client for Semantic Code Search.

Architecture Blueprint Reference: Phase 2 — Memgraph & Qdrant Integration.
This module handles all vector database operations against Qdrant:
  - Creating and managing the code embeddings collection.
  - Ingesting ASTNode embeddings with Payload metadata for filtering.
  - Semantic search with mandatory ABAC payload pre-filtering.

The embedding model runs locally via `fastembed` to uphold the
Data Minimization Security Guardrail — proprietary code never
leaves the machine during vectorization.
"""

import hashlib
from typing import Optional

from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    Range,
    VectorParams,
)

from dev_guardian.core.config import get_settings
from dev_guardian.core.logging import get_logger
from dev_guardian.parsers.models import ASTNode

logger = get_logger(__name__)

COLLECTION_NAME = "code_embeddings"


class QdrantCodeClient:
    """
    Vector database client for semantic code representations.

    Embeds AST entities locally and stores them in Qdrant with
    rich payload metadata (file_path, owner_team, clearance_level)
    enabling payload-filtered searches before the ANN executes.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        embedding_model: Optional[str] = None,
    ) -> None:
        """
        Initialize Qdrant client and local embedding model.

        Args:
            host: Qdrant server host.
            port: Qdrant gRPC/HTTP port.
            embedding_model: fastembed model name for local vectors.
        """
        settings = get_settings()
        self._host = host or settings.qdrant_host
        self._port = port or settings.qdrant_port
        self._model_name = embedding_model or settings.embedding_model

        self._client = QdrantClient(
            host=self._host,
            port=self._port,
        )
        self._embedder = TextEmbedding(
            model_name=self._model_name,
        )

        # Determine vector dimension from a test embedding
        test_vec = list(self._embedder.embed(["test"]))[0]
        self._vector_size = len(test_vec)

        logger.info(
            "qdrant_client_init",
            host=self._host,
            port=self._port,
            model=self._model_name,
            vector_dim=self._vector_size,
        )

    def ensure_collection(self) -> None:
        """
        Create the code_embeddings collection if it doesn't exist.

        Configures Cosine distance and payload indexes for ABAC
        metadata (clearance_level, owner_team, file_path).
        """
        collections = self._client.get_collections().collections
        exists = any(c.name == COLLECTION_NAME for c in collections)

        if not exists:
            self._client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=self._vector_size,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(
                "qdrant_collection_created",
                name=COLLECTION_NAME,
            )

        # Create payload indexes for fast ABAC filtering
        self._client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="clearance_level",
            field_schema=PayloadSchemaType.INTEGER,
        )
        self._client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="owner_team",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        self._client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="file_path",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        logger.info("qdrant_payload_indexes_created")

    def ingest_nodes(self, nodes: list[ASTNode]) -> int:
        """
        Embed and upsert a batch of ASTNodes into Qdrant.

        Each node's embedding text is composed from its name,
        type, file path, and docstring. Payload includes all
        ABAC metadata for pre-filtered semantic search.

        Batched internally in chunks of 500 to prevent OOM errors
        on very large repositories (like sktime).

        Args:
            nodes: List of ASTNode objects from the parser.

        Returns:
            Number of points upserted.
        """
        if not nodes:
            return 0

        import gc

        batch_size = 32  # Small batches to limit ONNX intermediate tensor RAM
        total_upserted = 0

        for i in range(0, len(nodes), batch_size):
            batch = nodes[i:i + batch_size]
            texts = [self._build_embedding_text(n) for n in batch]

            # Embed batch — ONNX allocates large intermediate tensors
            embeddings = list(self._embedder.embed(texts))

            points = []
            for node, vector in zip(batch, embeddings):
                point_id = self._stable_point_id(node)
                points.append(
                    PointStruct(
                        id=point_id,
                        vector=vector.tolist(),
                        payload={
                            "name": node.name,
                            "node_type": node.node_type.value,
                            "file_path": node.file_path,
                            "start_line": node.start_line,
                            "end_line": node.end_line,
                            "docstring": node.docstring or "",
                            "owner_team": node.owner_team,
                            "clearance_level": node.clearance_level,
                        },
                    )
                )

            self._client.upsert(
                collection_name=COLLECTION_NAME,
                points=points,
            )
            total_upserted += len(points)

            # Eagerly free ONNX intermediate buffers
            del embeddings, points, texts
            gc.collect()

        logger.info(
            "qdrant_nodes_ingested",
            count=total_upserted,
        )
        return total_upserted

    def semantic_search(
        self,
        query: str,
        user_clearance: int = 0,
        top_k: int = 5,
        owner_team: Optional[str] = None,
    ) -> list[dict]:
        """
        Search for semantically similar code entities.

        SECURITY: Results are pre-filtered by ABAC clearance
        level before the approximate nearest neighbor search
        executes, ensuring unauthorized nodes are never returned.

        Args:
            query: Natural language query (e.g., "tax calculator").
            user_clearance: Caller's ABAC clearance level.
            top_k: Number of results to return.
            owner_team: Optional team filter.

        Returns:
            List of scored result dictionaries.
        """
        query_vector = list(self._embedder.embed([query]))[0]

        must_conditions = [
            FieldCondition(
                key="clearance_level",
                range=Range(lte=user_clearance),
            ),
        ]

        if owner_team:
            must_conditions.append(
                FieldCondition(
                    key="owner_team",
                    match=MatchValue(value=owner_team),
                ),
            )

        results = self._client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector.tolist(),
            query_filter=Filter(must=must_conditions),
            limit=top_k,
        )

        return [
            {
                "score": r.score,
                "name": r.payload.get("name", ""),
                "node_type": r.payload.get("node_type", ""),
                "file_path": r.payload.get("file_path", ""),
                "docstring": r.payload.get("docstring", ""),
                "clearance_level": r.payload.get("clearance_level", 0),
            }
            for r in results.points
        ]

    def clear_collection(self) -> None:
        """Delete all points. Use for testing only."""
        self._client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=FilterSelector(filter=Filter(must=[])),
        )
        logger.warning("qdrant_collection_cleared")

    @staticmethod
    def _build_embedding_text(node: ASTNode) -> str:
        """
        Build the text string for embedding an AST entity.

        Combines the node's structural identity for optimal
        semantic similarity matching.
        """
        parts = [
            f"{node.node_type.value}: {node.name}",
            f"file: {node.file_path}",
        ]
        if node.docstring:
            parts.append(f"docs: {node.docstring}")
        return " | ".join(parts)

    @staticmethod
    def _stable_point_id(node: ASTNode) -> int:
        """Build a stable 63-bit point ID for deterministic upserts."""
        identity = f"{node.name}:{node.file_path}:{node.start_line}:{node.end_line}"
        digest = hashlib.sha256(identity.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], byteorder="big") & ((1 << 63) - 1)
