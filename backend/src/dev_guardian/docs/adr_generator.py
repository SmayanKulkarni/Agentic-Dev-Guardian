"""
ADR Generator — Phase 5.3: Auto-Generating Dynamic Documentation.

Generates Architectural Decision Records (ADRs) for the most structurally
significant functions/classes in a codebase, using Groq to narrate the
rationale based on the code source and its connected Memgraph graph context.

ADR format (MADR-style):
  - Status
  - Context
  - Decision
  - Consequences
"""

from __future__ import annotations

from pathlib import Path

from dev_guardian.core.logging import get_logger
from dev_guardian.graphrag.memgraph_client import MemgraphClient

logger = get_logger(__name__)


def get_top_complex_nodes(
    repo_path: Path,
    mg: MemgraphClient,
    top_n: int = 5,
    user_clearance: int = 0,
) -> list[dict]:
    """
    Query Memgraph for the highest blast-radius functions in the repo.

    Returns the top_n functions ordered by outgoing CALLS edge count,
    which represents structural complexity and downstream risk.

    Args:
        repo_path: Root of the indexed repository.
        mg: Active MemgraphClient.
        top_n: Number of nodes to return.
        user_clearance: ABAC clearance level.

    Returns:
        List of dicts with keys: name, file_path, start_line, end_line, call_count.
    """
    rows = mg.execute_query(
        """
        MATCH (n:ASTNode)-[:CALLS]->(callee:ASTNode)
        WHERE n.node_type IN ["function", "method"]
          AND n.clearance_level <= $cl
          AND n.file_path STARTS WITH $root
        RETURN
            n.name AS name,
            n.file_path AS file_path,
            n.start_line AS start_line,
            n.end_line AS end_line,
            count(callee) AS call_count
        ORDER BY call_count DESC
        LIMIT $top_n
        """,
        {"root": str(repo_path), "cl": user_clearance, "top_n": top_n},
    )

    logger.info("adr_top_nodes_fetched", count=len(rows))
    return rows


def generate_adr(
    node_name: str,
    node_source: str,
    graphrag_context: str,
) -> str:
    """
    Generate an ADR markdown section for a single function/class.

    Args:
        node_name: Name of the function or class.
        node_source: Raw source code string.
        graphrag_context: Structural context (callers, related nodes).

    Returns:
        A formatted ADR markdown string.
    """
    try:
        from dev_guardian.harness.skill_router import run_skill
        result = run_skill(
            "adr_generator",
            {
                "node_name": node_name,
                "node_source": node_source[:1500],
                "graphrag_context": graphrag_context[:800],
            },
        )
        from dev_guardian.harness.schema import ADRDraft
        parsed: ADRDraft = result.parsed  # type: ignore[assignment]
        adr_body = (
            f"## Status\nAccepted\n\n"
            f"## Context\n{parsed.context}\n\n"
            f"## Decision\n{parsed.decision}\n\n"
            f"## Consequences\n{parsed.consequences}"
        )
        logger.info("adr_generated", name=node_name)
        return f"### ADR: `{node_name}`\n\n{adr_body}\n"
    except Exception as exc:
        logger.warning("adr_generation_failed", name=node_name, error=str(exc))
        return (
            f"### ADR: `{node_name}`\n\n"
            f"## Status\nDraft\n\n"
            f"## Context\n_ADR generation failed: {str(exc)[:120]}_\n"
        )
