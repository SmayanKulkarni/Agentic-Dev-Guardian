"""
MCP Server for Agentic Dev Guardian.

Architecture Blueprint Reference: Phase 4 — MCP Server Integration.
Wraps the internal GraphRAG retrieval engine and the LangGraph MoA
evaluation pipeline into Anthropic Model Context Protocol (MCP) tools,
resources, and prompts — enabling any MCP-compatible IDE (Cursor,
Claude Desktop, Windsurf) to natively query, evaluate, and govern
codebases in real-time.

Entry Points:
    - ``guardian serve`` CLI command starts the stdio transport.
    - IDE clients connect via MCP stdio or SSE.

Security:
    - All queries enforce ABAC clearance filtering.
    - Raw proprietary code is NEVER sent to the LLM; only AST-derived
      context is transmitted (Data Minimization Guardrail).
"""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from dev_guardian.core.config import get_settings
from dev_guardian.core.logging import get_logger

logger = get_logger(__name__)

# ── Initialize the MCP Server ──────────────────────────────────────
mcp = FastMCP("Agentic Dev Guardian")


# ═══════════════════════════════════════════════════════════════════
#  TOOLS — Executable functions the IDE agent can invoke
# ═══════════════════════════════════════════════════════════════════


@mcp.tool()
def query_guardian_graph(
    query: str,
    clearance: int = 0,
    top_k: int = 5,
) -> str:
    """Search the codebase knowledge graph using hybrid GraphRAG retrieval.

    Performs a dual-database query combining Qdrant semantic vector search
    with Memgraph structural AST graph traversal. Returns merged context
    showing relevant functions, classes, and their dependency relationships.

    Use this tool when you need to understand codebase structure, find
    related functions, trace dependency chains, or assess the blast radius
    of a proposed change.

    Args:
        query: Natural language description of what you are looking for
               in the codebase (e.g., "authentication middleware",
               "database connection pooling", "payment processing").
        clearance: ABAC security clearance level (0=public, higher=restricted).
                   Only entities at or below this clearance level are returned.
        top_k: Maximum number of semantic search results to retrieve.

    Returns:
        A structured text block containing semantic search hits and
        structural graph context, ready for LLM reasoning.
    """
    from dev_guardian.graphrag.hybrid_retriever import HybridRetriever

    logger.info(
        "mcp_query_graph",
        query=query,
        clearance=clearance,
        top_k=top_k,
    )

    try:
        retriever = HybridRetriever()
        result = retriever.retrieve(
            query=query,
            user_clearance=clearance,
            top_k=top_k,
        )
        return result.get("merged_context", "No results found.")
    except Exception as exc:
        error_msg = (
            f"[Guardian Error] GraphRAG query failed: {exc}. "
            "Ensure Memgraph and Qdrant are running and the codebase "
            "has been indexed with `guardian index <path>`."
        )
        logger.error("mcp_query_graph_error", error=str(exc))
        return error_msg


@mcp.tool()
def evaluate_pr_diff(
    diff_content: str,
    repo_path: str = ".",
    clearance: int = 0,
) -> str:
    """Evaluate a Pull Request diff using the full MoA agent pipeline.

    Runs the complete Mixture-of-Agents evaluation pipeline:
    1. Retrieves GraphRAG context for the changed code.
    2. Gatekeeper Agent checks for architectural violations.
    3. Red Team Tester Agent generates adversarial test cases.
    4. Supervisor merges reports and routes to debate or remediation.
    5. If rejected, the Remediation Specialist generates a corrected diff.

    Use this tool when a developer submits code changes and you need
    to verify they are safe, architecturally consistent, and well-tested
    before merging.

    Args:
        diff_content: The raw unified diff string (e.g., output of
                      ``git diff`` or a PR diff from GitHub).
        repo_path: Absolute path to the indexed repository root.
        clearance: ABAC security clearance level of the requesting user.

    Returns:
        A JSON string containing the pipeline decision (approve/remediate),
        agent messages, and any remediation diff if applicable.
    """
    from dev_guardian.agents.graph import build_guardian_graph
    from dev_guardian.graphrag.hybrid_retriever import HybridRetriever

    logger.info(
        "mcp_evaluate_diff",
        diff_length=len(diff_content),
        repo_path=repo_path,
    )

    try:
        # Retrieve GraphRAG context
        retriever = HybridRetriever()
        rag_result = retriever.retrieve(
            query=diff_content[:500],
            user_clearance=clearance,
            top_k=10,
        )
        context = rag_result.get("merged_context", "")

        # Build and invoke the MoA pipeline
        graph = build_guardian_graph()
        result = graph.invoke(
            {
                "pr_diff": diff_content,
                "repo_path": repo_path,
                "user_clearance": clearance,
                "graphrag_context": context,
                "messages": [],
            }
        )

        # Format output
        output = {
            "decision": result.get("decision", "unknown"),
            "messages": result.get("messages", []),
            "remediation_diff": result.get("remediation_diff", ""),
            "gatekeeper_verdict": result.get("gatekeeper_report", {}).get(
                "verdict", ""
            ),
            "redteam_verdict": result.get("redteam_report", {}).get("verdict", ""),
        }

        return json.dumps(output, indent=2)

    except Exception as exc:
        error_msg = (
            f"[Guardian Error] PR evaluation failed: {exc}. "
            "Ensure all services (Memgraph, Qdrant, Groq) are available "
            "and the repository has been indexed."
        )
        logger.error("mcp_evaluate_error", error=str(exc))
        return json.dumps({"error": error_msg})


@mcp.tool()
def impact_analysis(
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
        error_msg = (
            f"[Guardian Error] Impact analysis failed: {exc}. "
            "Ensure Memgraph is running and the codebase has been indexed."
        )
        logger.error("mcp_impact_error", error=str(exc))
        return error_msg


@mcp.tool()
def index_codebase(
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
        error_msg = f"[Guardian Error] Indexing failed: {exc}"
        logger.error("mcp_index_error", error=str(exc))
        return error_msg


# ═══════════════════════════════════════════════════════════════════
#  RESOURCES — Dynamic context the IDE can read passively
# ═══════════════════════════════════════════════════════════════════


@mcp.resource("guardian://status")
def get_guardian_status() -> str:
    """Current operational status of the Agentic Dev Guardian system.

    Returns connectivity status for all backend services and the
    current configuration state.
    """
    settings = get_settings()
    status = {
        "version": "0.1.0",
        "groq_configured": bool(settings.groq_api_key),
        "langfuse_configured": bool(settings.langfuse_public_key),
        "memgraph_endpoint": f"{settings.memgraph_host}:{settings.memgraph_port}",
        "qdrant_endpoint": f"{settings.qdrant_host}:{settings.qdrant_port}",
        "embedding_model": settings.embedding_model,
        "capabilities": [
            "query_guardian_graph",
            "evaluate_pr_diff",
            "impact_analysis",
            "index_codebase",
        ],
    }
    return json.dumps(status, indent=2)


@mcp.resource("guardian://security-policy")
def get_security_policy() -> str:
    """Repository security policy and architectural constraints.

    Returns the ABAC access control rules and data minimization
    guardrails enforced by the Guardian system. The IDE agent should
    reference these rules when evaluating code changes.
    """
    policy = (
        "# Agentic Dev Guardian — Security Policy\n\n"
        "## ABAC Access Control\n"
        "- Every GraphRAG query enforces `WHERE node.clearance <= $user_clearance`.\n"
        "- Agents operate on Just-In-Time Read-Only tokens scoped to the PR diff.\n"
        "- clearance=0 is public, higher values access restricted contexts.\n\n"
        "## Data Minimization\n"
        "- Raw proprietary code is NEVER sent to external LLMs.\n"
        "- Only AST-derived structural metadata and semantic embeddings are "
        "transmitted.\n"
        "- Embeddings are generated locally using FastEmbed "
        "(jinaai/jina-embeddings-v2-base-code).\n\n"
        "## Architectural Invariants\n"
        "- Frontend UI components must NOT directly import database models.\n"
        "- Payment services must NOT use synchronous HTTP calls.\n"
        "- All public API endpoints must have authentication middleware.\n"
        "- Database migrations must include a rollback strategy.\n"
    )
    return policy


# ═══════════════════════════════════════════════════════════════════
#  PROMPTS — Pre-defined system instructions for common workflows
# ═══════════════════════════════════════════════════════════════════


@mcp.prompt()
def review_pr(diff: str) -> str:
    """Generate a comprehensive PR review using the Guardian pipeline.

    This prompt template instructs the IDE agent to:
    1. Query the knowledge graph for context.
    2. Evaluate the diff through the MoA pipeline.
    3. Present results in a structured review format.
    """
    return (
        "You are reviewing a Pull Request using the Agentic Dev Guardian system.\n\n"
        "## Instructions\n"
        "1. First, call `query_guardian_graph` with a summary of the diff to "
        "   understand the affected codebase area.\n"
        "2. Then, call `evaluate_pr_diff` with the full diff content.\n"
        "3. Present the results as a structured code review with:\n"
        "   - Decision (APPROVE / REMEDIATE)\n"
        "   - Architectural violations found\n"
        "   - Adversarial test cases generated\n"
        "   - Suggested fixes (if any)\n\n"
        f"## PR Diff\n```diff\n{diff}\n```"
    )


@mcp.prompt()
def investigate_function(function_name: str) -> str:
    """Deep-dive investigation into a specific function's role and impact.

    Instructs the IDE agent to perform impact analysis and retrieve
    all contextual information about a function.
    """
    return (
        f"Investigate the function `{function_name}` in the codebase.\n\n"
        "## Instructions\n"
        f"1. Call `impact_analysis` for `{function_name}` to find all "
        "   downstream dependencies.\n"
        f'2. Call `query_guardian_graph` with "{function_name}" to get '
        "   semantic context.\n"
        "3. Summarize:\n"
        f"   - What `{function_name}` does\n"
        "   - What depends on it (blast radius)\n"
        "   - Risks of modifying it\n"
        "   - Suggested refactoring approach (if applicable)\n"
    )


# ═══════════════════════════════════════════════════════════════════
#  SERVER ENTRY POINT
# ═══════════════════════════════════════════════════════════════════


def run_server() -> None:
    """Start the MCP server using stdio transport.

    Called by the ``guardian serve`` CLI command.
    The server listens on stdin/stdout for MCP protocol messages
    from the connected IDE client.
    """
    logger.info("mcp_server_starting")
    mcp.run(transport="stdio")
