"""
Hybrid GraphRAG Retriever.

Architecture Blueprint Reference: Phase 2 — Memgraph & Qdrant Integration.
This module implements the unified retrieval class that queries BOTH
Memgraph (structural graph) and Qdrant (semantic vectors) simultaneously,
then merges the results into a single context payload for the LLM.

This is the core "GraphRAG" pattern:
  - Qdrant answers "fuzzy" questions  → "Which function handles tax?"
  - Memgraph answers "exact" questions → "What calls calculate_tax()?"
  - The merged context gives the LLM both precision and recall.
"""

from typing import Optional

from dev_guardian.core.logging import get_logger
from dev_guardian.graphrag.memgraph_client import MemgraphClient
from dev_guardian.graphrag.qdrant_client import QdrantCodeClient
from dev_guardian.parsers.models import ParseResult

logger = get_logger(__name__)


class HybridRetriever:
    """
    Unified GraphRAG retriever merging graph + vector results.

    Combines structural Cypher queries (Memgraph) with semantic
    vector search (Qdrant) and de-duplicates results into a
    single context block suitable for LLM consumption.
    """

    def __init__(
        self,
        memgraph: Optional[MemgraphClient] = None,
        qdrant: Optional[QdrantCodeClient] = None,
    ) -> None:
        """
        Initialize with Memgraph and Qdrant clients.

        If not provided, defaults are created from config.

        Args:
            memgraph: Optional pre-configured MemgraphClient.
            qdrant: Optional pre-configured QdrantCodeClient.
        """
        self._memgraph = memgraph or MemgraphClient()
        self._qdrant = qdrant or QdrantCodeClient()
        logger.info("hybrid_retriever_init")

    def ingest(self, parse_result: ParseResult) -> dict:
        """
        Ingest a ParseResult into both databases.

        Sends AST Nodes/Edges to Memgraph and embeds Nodes
        into Qdrant for semantic search.

        Args:
            parse_result: The Phase 1 AST parsing output.

        Returns:
            Dictionary summarizing ingestion counts.
        """
        # Ensure infrastructure is ready
        self._memgraph.ensure_indexes()
        self._qdrant.ensure_collection()

        # Ingest into Memgraph (structural graph)
        graph_stats = self._memgraph.ingest_parse_result(parse_result)

        # Ingest into Qdrant (semantic vectors)
        vector_count = self._qdrant.ingest_nodes(parse_result.nodes)

        summary = {
            "graph_nodes": graph_stats["nodes_ingested"],
            "graph_edges": graph_stats["edges_ingested"],
            "vectors_embedded": vector_count,
        }
        logger.info("hybrid_ingest_complete", **summary)
        return summary

    def retrieve(
        self,
        query: str,
        user_clearance: int = 0,
        top_k: int = 5,
    ) -> dict:
        """
        Execute a hybrid retrieval combining both databases.

        1. Run a semantic search on Qdrant to find fuzzy matches.
        2. For each semantic hit, run a structural impact query
           on Memgraph to find connected graph entities.
        3. Merge and de-duplicate results.

        SECURITY: Both queries enforce ABAC clearance filtering.

        Args:
            query: Natural language query.
            user_clearance: Caller's ABAC clearance level.
            top_k: Max semantic results from Qdrant.

        Returns:
            Dictionary with semantic_hits, graph_context,
            and a merged context string for LLM consumption.
        """
        # Step 1: Semantic search (Qdrant)
        semantic_hits = self._qdrant.semantic_search(
            query=query,
            user_clearance=user_clearance,
            top_k=top_k,
        )

        # Step 2: Structural expansion (Memgraph)
        graph_context: list[dict] = []
        seen_names: set[str] = set()

        for hit in semantic_hits:
            name = hit.get("name", "")
            if not name or name in seen_names:
                continue
            seen_names.add(name)

            # Direct node lookup
            nodes = self._memgraph.query_node_by_name(
                name=name,
                user_clearance=user_clearance,
            )
            graph_context.extend(nodes)

            # Impact analysis
            impacted = self._memgraph.query_impact_analysis(
                function_name=name,
                user_clearance=user_clearance,
                max_depth=2,
            )
            for imp in impacted:
                imp_name = imp.get("name", "")
                if imp_name not in seen_names:
                    seen_names.add(imp_name)
                    graph_context.append(imp)

        # Step 3: Merge into LLM-ready context
        merged_context = self._build_context_string(semantic_hits, graph_context)

        logger.info(
            "hybrid_retrieve_complete",
            query=query,
            semantic_hits=len(semantic_hits),
            graph_entities=len(graph_context),
        )

        return {
            "semantic_hits": semantic_hits,
            "graph_context": graph_context,
            "merged_context": merged_context,
        }

    @staticmethod
    def _build_context_string(
        semantic_hits: list[dict],
        graph_context: list[dict],
    ) -> str:
        """
        Build a structured context string for LLM consumption.

        Formats both semantic and structural results into a
        clean text block that can be injected into an LLM prompt.
        """
        lines = ["## Semantic Search Results"]
        for i, hit in enumerate(semantic_hits, 1):
            lines.append(
                f"{i}. [{hit.get('node_type', '?')}] "
                f"`{hit.get('name', '?')}` "
                f"in {hit.get('file_path', '?')} "
                f"(score: {hit.get('score', 0):.3f})"
            )
            if hit.get("docstring"):
                lines.append(f"   → {hit['docstring'][:120]}")

        lines.append("")
        lines.append("## Structural Graph Context")
        for entity in graph_context:
            lines.append(
                f"- [{entity.get('node_type', '?')}] "
                f"`{entity.get('name', '?')}` "
                f"in {entity.get('file_path', '?')}"
            )

        return "\n".join(lines)
