"""
Codebase Intelligence Capability Cluster.

Exposes: impact_analysis, index_codebase, audit_codebase, generate_architecture_docs
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
    from dev_guardian.graphrag.clients import get_memgraph, reset_clients

    logger.info(
        "mcp_impact_analysis",
        function_name=function_name,
        max_depth=max_depth,
    )

    try:
        impacted = get_memgraph().query_impact_analysis(
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
        reset_clients()
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
    from dev_guardian.graphrag.clients import get_retriever, reset_clients
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

        summary = get_retriever().ingest(results)

        return (
            f"Indexed {results.total_files} files — "
            f"{summary['graph_nodes']} Memgraph Nodes, "
            f"{summary['graph_edges']} Memgraph Edges, "
            f"{summary['vectors_embedded']} Qdrant Vectors."
        )

    except Exception as exc:
        reset_clients()
        logger.error("mcp_index_error", error=str(exc))
        return f"[Guardian Error] Indexing failed: {exc}"


def _audit_codebase(
    path: str,
    top: int = 5,
    clearance: int = 0,
    output: str = "",
) -> str:
    """Audit a repository's highest-risk functions for bugs and bad patterns.

    Ranks functions by blast radius (how many calls they make), reads each
    one from disk, and runs it through the Gatekeeper and Red Team agents as
    a synthetic diff. This is the proactive counterpart to evaluate_pr_diff:
    it finds problems in code that is already merged, before anyone opens a PR.

    The repository must already be indexed — call index_codebase first if a
    run returns no findings.

    Args:
        path: Absolute path to the indexed repository root.
        top: How many of the highest blast-radius functions to audit.
             Each one costs several LLM calls, so keep this small.
        clearance: ABAC security clearance level.
        output: Optional file path to also write the markdown report to.
                Leave empty to only return it.

    Returns:
        The markdown audit report, prefixed with a one-line severity tally.
    """
    from dev_guardian.audit import run_audit

    logger.info("mcp_audit_codebase", path=path, top=top)

    try:
        target = Path(path)
        if not target.is_dir():
            return (
                f"[Guardian Error] Path does not exist or is not a directory: {path}"
            )

        report = run_audit(path=target, top=top, clearance=clearance)

        if output:
            Path(output).write_text(report.markdown, encoding="utf-8")

        counts = report.counts
        tally = (
            f"{counts['high']} high, {counts['medium']} medium, "
            f"{counts['error']} errored, {counts['pass']} pass"
        )
        written = f" Report written to {output}." if output else ""
        return f"Audited {len(report.findings)} functions: {tally}.{written}\n\n{report.markdown}"

    except Exception as exc:
        logger.error("mcp_audit_error", error=str(exc))
        return f"[Guardian Error] Audit failed: {exc}"


def _generate_architecture_docs(
    path: str,
    top: int = 5,
    clearance: int = 0,
    output: str = "",
) -> str:
    """Generate an architecture wiki from the indexed graph.

    Reads the already-indexed Memgraph AST graph — no re-parsing — and
    narrates it into markdown containing a module dependency flowchart, the
    class inheritance hierarchy, call graphs for the top-N functions (all as
    Mermaid diagrams), and LLM-written Architectural Decision Records.

    Use this to onboard onto an unfamiliar repository, or to refresh
    architecture docs after a structural change.

    Args:
        path: Absolute path to the indexed repository root.
        top: How many of the highest-complexity functions to write ADRs for.
        clearance: ABAC security clearance level.
        output: Optional file path to also write the wiki to (the CLI
                default is GUARDIAN_WIKI.md). Leave empty to only return it.

    Returns:
        The generated wiki markdown.
    """
    from dev_guardian.docs.wiki_builder import build_wiki, save_wiki
    from dev_guardian.graphrag.memgraph_client import MemgraphClient

    logger.info("mcp_generate_docs", path=path, top=top)

    try:
        target = Path(path)
        if not target.is_dir():
            return (
                f"[Guardian Error] Path does not exist or is not a directory: {path}"
            )

        wiki = build_wiki(
            repo_path=target,
            mg=MemgraphClient(),
            top_n=top,
            user_clearance=clearance,
        )

        if output:
            written = save_wiki(wiki, Path(output))
            return f"Wiki written to {written}.\n\n{wiki}"
        return wiki

    except Exception as exc:
        logger.error("mcp_docs_error", error=str(exc))
        return (
            f"[Guardian Error] Documentation generation failed: {exc}. "
            "Ensure Memgraph is running and the codebase has been indexed."
        )


# ── Cluster registration entry ──────────────────────────────────────

CLUSTER_REGISTRY["codebase_intelligence"] = {
    "description": (
        "Codebase structural analysis: blast-radius impact analysis, "
        "on-demand GraphRAG re-indexing, proactive red-team audit of the "
        "riskiest functions, and generated architecture documentation."
    ),
    "tools": {
        "impact_analysis": _impact_analysis,
        "index_codebase": _index_codebase,
        "audit_codebase": _audit_codebase,
        "generate_architecture_docs": _generate_architecture_docs,
    },
    "prompts": ["investigate_function"],
}
