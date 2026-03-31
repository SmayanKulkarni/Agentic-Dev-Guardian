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

from pathlib import Path

from groq import Groq

from dev_guardian.core.config import get_settings
from dev_guardian.core.logging import get_logger
from dev_guardian.graphrag.memgraph_client import MemgraphClient

logger = get_logger(__name__)

_ADR_SYSTEM_PROMPT = """\
You are an expert software architect writing an Architectural Decision Record (ADR).
Given a function/class source code and its graph context (callers, callees, and
related nodes from a structural AST knowledge graph), write a concise ADR in
this exact markdown format:

## Status
Accepted

## Context
[1-2 sentences: Why does this function/class exist? What problem does it solve?]

## Decision
[2-3 sentences: What architectural pattern does this code implement? Why this approach?]

## Consequences
[2-3 sentences: What are the structural trade-offs, risks, or downstream impacts?]

Keep each section to 2-3 sentences maximum. Be precise and technical.
"""


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
    groq_client: Groq,
    model: str = "llama-3.3-70b-versatile",
) -> str:
    """
    Generate an ADR markdown section for a single function/class.

    Sends the source code and its Memgraph-derived graph context to Groq,
    which narrates the architectural rationale in structured ADR format.

    Args:
        node_name: Name of the function or class.
        node_source: Raw source code string.
        graphrag_context: Structural context (callers, related nodes).
        groq_client: Initialized Groq client.
        model: Groq model to use.

    Returns:
        A formatted ADR markdown string.
    """
    user_msg = (
        f"Function/Class: `{node_name}`\n\n"
        f"### Source Code\n```python\n{node_source[:1500]}\n```\n\n"
        f"### Graph Context (from Memgraph)\n{graphrag_context[:800]}"
    )

    try:
        response = groq_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _ADR_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
            max_tokens=500,
        )
        adr_body = response.choices[0].message.content.strip()
        logger.info("adr_generated", name=node_name)
        return f"### ADR: `{node_name}`\n\n{adr_body}\n"
    except Exception as exc:
        logger.warning("adr_generation_failed", name=node_name, error=str(exc))
        return (
            f"### ADR: `{node_name}`\n\n"
            f"## Status\nDraft\n\n"
            f"## Context\n_ADR generation failed: {str(exc)[:120]}_\n"
        )
