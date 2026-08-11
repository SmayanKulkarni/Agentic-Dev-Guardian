"""
Structure Explainer — Phase 5.3: Auto-Generating Dynamic Documentation.

Replaces the legacy Mermaid Diagram Generator.
Queries the live Kùzu AST graph and feeds the raw structural edges
(IMPORTS, CALLS, INHERITS_FROM) directly to Groq to generate a concise,
human-readable architectural summary.
"""

from __future__ import annotations

from pathlib import Path

from dev_guardian.core.logging import get_logger
from dev_guardian.graphrag.kuzu_client import KuzuClient

logger = get_logger(__name__)


def explain_module_dependencies(
    repo_path: Path, graph: KuzuClient, user_clearance: int = 0
) -> str:
    """
    Generate an AI-narrated summary of inter-module import relationships.
    """
    rows = graph.execute_query(
        """
        MATCH (a:ASTNode)-[:IMPORTS]->(b:ASTNode)
        WHERE a.file_path STARTS WITH $root
          AND a.clearance_level <= $cl
          AND b.clearance_level <= $cl
        RETURN
            a.file_path AS src_file,
            b.file_path AS dst_file
        LIMIT 300
        """,
        {"root": str(repo_path), "cl": user_clearance},
    )

    if not rows:
        return "*No inter-module import relationships were found in the graph.*"

    edges = set()
    for row in rows:
        src = Path(row["src_file"]).stem if row.get("src_file") else "unknown"
        dst = Path(row["dst_file"]).stem if row.get("dst_file") else "unknown"
        if src != dst:
            edges.add((src, dst))

    edge_text = "\n".join([f"- {src} imports {dst}" for src, dst in sorted(edges)])

    return _call_structure_explainer(
        analysis_type="module_dependencies",
        edge_text=edge_text,
        task_description=(
            "Write a single, concise professional paragraph summarizing the high-level "
            "architecture of these modules. What are the core dependencies? Which modules "
            "act as central hubs? Do not list every single import, just synthesize the structural story."
        ),
        log_key="explainer_module_graph_generated",
        log_kwargs={"edge_count": len(edges)},
    )


def explain_call_graph(
    function_name: str,
    graph: KuzuClient,
    depth: int = 2,
    user_clearance: int = 0,
) -> str:
    """
    Generate an AI-narrated execution trace of a function.
    """
    rows = graph.execute_query(
        f"""
        MATCH (root:ASTNode)-[:CALLS*0..{max(depth - 1, 0)}]->(caller:ASTNode)
              -[:CALLS]->(callee:ASTNode)
        WHERE root.name = $fn
          AND root.clearance_level <= $cl
          AND callee.clearance_level <= $cl
        RETURN DISTINCT caller.name AS caller, callee.name AS callee
        LIMIT 80
        """,
        {"fn": function_name, "cl": user_clearance},
    )

    if not rows:
        return "*No outgoing execution calls were found in the graph.*"

    edges = set()
    for row in rows:
        caller = row.get("caller", "?")
        callee = row.get("callee", "?")
        if caller and callee:
            edges.add((caller, callee))

    edge_text = "\n".join(
        [f"- `{caller}()` calls `{callee}()`" for caller, callee in sorted(edges)]
    )

    return _call_structure_explainer(
        analysis_type="call_graph",
        edge_text=edge_text,
        task_description=(
            f"Write a concise professional paragraph explaining the execution flow of "
            f"`{function_name}` based on these calls. What subsystems does it trigger? "
            "What is its primary structural role? Be brief and technical."
        ),
        log_key="explainer_call_graph_generated",
        log_kwargs={"fn": function_name, "edge_count": len(edges)},
    )


def explain_class_hierarchy(
    repo_path: Path, graph: KuzuClient, user_clearance: int = 0
) -> str:
    """
    Generate an AI-narrated summary of the object-oriented heritage.
    """
    rows = graph.execute_query(
        """
        MATCH (child:ASTNode)-[:INHERITS_FROM]->(parent:ASTNode)
        WHERE child.file_path STARTS WITH $root
          AND child.clearance_level <= $cl
        RETURN child.name AS child, parent.name AS parent
        LIMIT 100
        """,
        {"root": str(repo_path), "cl": user_clearance},
    )

    if not rows:
        return "*No class inheritance relationships were found in the graph.*"

    lines = []
    for row in rows:
        child = row.get("child", "?")
        parent = row.get("parent", "?")
        if child and parent:
            lines.append(f"- Class `{child}` inherits from `{parent}`")

    edge_text = "\n".join(lines)

    return _call_structure_explainer(
        analysis_type="class_hierarchy",
        edge_text=edge_text,
        task_description=(
            "Write a single concise professional paragraph summarizing this hierarchy. "
            "What are the dominant base classes? Are there deep inheritance trees or flat mixins? "
            "Evaluate the architectural shape of the OOP design based only on this data."
        ),
        log_key="explainer_class_hierarchy_generated",
        log_kwargs={"row_count": len(rows)},
    )


def _call_structure_explainer(
    *,
    analysis_type: str,
    edge_text: str,
    task_description: str,
    log_key: str,
    log_kwargs: dict,
) -> str:
    """Shared harness LLM call for all structure explainer functions."""
    try:
        from dev_guardian.harness.skill_router import run_skill
        result = run_skill(
            "structure_explainer",
            {
                "analysis_type": analysis_type,
                "edge_text": edge_text,
                "task_description": task_description,
            },
        )
        explanation = result.parsed.explanation  # type: ignore[attr-defined]
        logger.info(log_key, **log_kwargs)
        return explanation
    except Exception as exc:
        logger.error("structure_explainer_failed", error=str(exc))
        return f"*Error generating explanation: {exc}*\n\nRaw Data:\n{edge_text}"
