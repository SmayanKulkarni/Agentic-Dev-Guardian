"""
Codebase Intelligence Capability Cluster.

Exposes: impact_analysis, index_codebase
Domain : "codebase_intelligence"

Loaded JIT when the IDE agent calls equip_capability("codebase_intelligence").
"""

from __future__ import annotations

from pathlib import Path

from dev_guardian.capability_clusters.core import CLUSTER_REGISTRY
from dev_guardian.core.logging import get_logger

logger = get_logger(__name__)

# ── Tool implementations ────────────────────────────────────────────


def _impact_analysis(
    function_name: str,
    clearance: int = 0,
    max_depth: int = 3,
) -> str:
    """Analyze the blast radius of modifying a specific function.

    Traverses the Memgraph AST knowledge graph to find all functions,
    classes, and modules that directly or transitively depend on the
    specified function. This reveals the full impact of changing or
    deleting a function.

    Use this tool before making changes to understand what could break.

    Args:
        function_name: The exact name of the function to analyze
                       (e.g., "calculate_tax", "UserService.authenticate").
        clearance: ABAC security clearance level.
        max_depth: Maximum graph traversal depth for transitive dependencies.

    Returns:
        A structured list of all impacted entities with their types,
        file paths, and relationship chains.
    """
    from dev_guardian.graphrag.memgraph_client import MemgraphClient

    logger.info(
        "mcp_impact_analysis",
        function_name=function_name,
        max_depth=max_depth,
    )

    try:
        client = MemgraphClient()
        impacted = client.query_impact_analysis(
            function_name=function_name,
            user_clearance=clearance,
            max_depth=max_depth,
        )

        if not impacted:
            return f"No downstream dependencies found for `{function_name}`."

        lines = [f"## Impact Analysis: `{function_name}`", ""]
        for i, entity in enumerate(impacted, 1):
            lines.append(
                f"{i}. [{entity.get('node_type', '?')}] "
                f"`{entity.get('name', '?')}` "
                f"in {entity.get('file_path', '?')}"
            )
        return "\n".join(lines)

    except Exception as exc:
        logger.error("mcp_impact_error", error=str(exc))
        return (
            f"[Guardian Error] Impact analysis failed: {exc}. "
            "Ensure Memgraph is running and the codebase has been indexed."
        )


def _index_codebase(
    path: str,
    language: str = "python",
) -> str:
    """Parse and index a codebase into the GraphRAG knowledge graph.

    Uses Tree-sitter to deterministically extract AST nodes (functions,
    classes, variables) and edges (calls, imports, inheritance), then
    ingests them into Memgraph (structural graph) and Qdrant (semantic
    vectors).

    Use this tool to initialize or refresh the knowledge graph after
    code changes.

    Args:
        path: Absolute path to the codebase directory to parse and index.
        language: Programming language to parse (currently: "python").

    Returns:
        A summary of the indexing results including node, edge, and
        vector counts.
    """
    from dev_guardian.graphrag.hybrid_retriever import HybridRetriever
    from dev_guardian.parsers.ast_parser import ASTParser

    logger.info("mcp_index_codebase", path=path, language=language)

    try:
        target = Path(path)
        if not target.is_dir():
            return (
                f"[Guardian Error] Path does not exist or is not a directory: {path}"
            )

        parser = ASTParser(language=language)
        results = parser.parse_directory(target)

        retriever = HybridRetriever()
        summary = retriever.ingest(results)

        return (
            f"Indexed {results.total_files} files — "
            f"{summary['graph_nodes']} Memgraph Nodes, "
            f"{summary['graph_edges']} Memgraph Edges, "
            f"{summary['vectors_embedded']} Qdrant Vectors."
        )

    except Exception as exc:
        logger.error("mcp_index_error", error=str(exc))
        return f"[Guardian Error] Indexing failed: {exc}"


# ── Cluster registration entry ──────────────────────────────────────

CLUSTER_REGISTRY["codebase_intelligence"] = {
    "description": (
        "Codebase structural analysis: blast-radius impact analysis and "
        "on-demand GraphRAG re-indexing of a repository."
    ),
    "tools": {
        "impact_analysis": _impact_analysis,
        "index_codebase": _index_codebase,
    },
    "prompts": ["investigate_function"],
}
