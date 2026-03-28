"""
Self-Healing Capability Cluster.

Exposes: analyze_blast_radius, generate_refactor_blueprint, list_refactor_patterns
Domain : "self_healing"

Loaded JIT when the IDE agent calls equip_capability("self_healing").
"""

from __future__ import annotations

import json

from dev_guardian.agents.refactor_patterns import list_patterns
from dev_guardian.capability_clusters.core import CLUSTER_REGISTRY
from dev_guardian.core.logging import get_logger

logger = get_logger(__name__)


# ── Tool implementations ─────────────────────────────────────────────


def _list_refactor_patterns() -> str:
    """List all available built-in migration patterns.

    Returns a JSON array of available pattern keys and their descriptions.
    Use this before calling `generate_refactor_blueprint` to pick the right
    pattern for your migration need.

    Returns:
        JSON array of {key, description} objects.
    """
    patterns = list_patterns()
    return json.dumps(patterns, indent=2)


def _analyze_blast_radius(
    pattern: str,
    repo_path: str = ".",
    function_name: str = "",
) -> str:
    """Analyze the blast radius of a migration pattern using Memgraph.

    Runs the pattern's Cypher query against the indexed knowledge graph
    and returns the list of ALL impacted AST entities. This is a pure
    deterministic graph query — no LLM is used.

    Use this first to understand the scope of a migration before
    generating a full blueprint.

    Args:
        pattern: Migration pattern key (use list_refactor_patterns() to see options).
        repo_path: Absolute path to the indexed repository root.
        function_name: Required only for the 'deprecate-function' pattern.

    Returns:
        JSON with the impacted entity count and entity list.
    """
    from dev_guardian.agents.refactor_patterns import get_pattern
    from dev_guardian.graphrag.memgraph_client import MemgraphClient

    logger.info("mcp_analyze_blast_radius", pattern=pattern, repo_path=repo_path)

    pattern_def = get_pattern(pattern)
    if not pattern_def:
        available = [p["key"] for p in list_patterns()]
        return json.dumps({"error": f"Unknown pattern '{pattern}'. Available: {available}"})

    try:
        client = MemgraphClient()
        params: dict = {"repo_path": repo_path}
        if function_name:
            params["function_name"] = function_name
        rows = client.execute_query(pattern_def["cypher"].strip(), params)
    except Exception as exc:
        return json.dumps({"error": f"Graph query failed: {exc}"})

    return json.dumps(
        {
            "pattern": pattern,
            "description": pattern_def["description"],
            "total_impacted": len(rows),
            "entities": rows[:50],  # cap for token budget; full run in blueprint
        },
        indent=2,
    )


def _generate_refactor_blueprint(
    pattern: str,
    repo_path: str = ".",
    function_name: str = "",
) -> str:
    """Run the full Self-Healing refactor pipeline and generate a Markdown Blueprint.

    Executes the 3-agent LangGraph pipeline:
      1. RefactorPlanner → deterministic blast-radius analysis via Memgraph.
      2. MigrationScribe → file-by-file Markdown migration instructions via Groq.
      3. BlueprintValidator → sanity-checks the blueprint against the graph.

    The blueprint is ready to hand directly to your IDE agent (Gemini/Claude)
    to execute the actual code changes.

    Args:
        pattern: Migration pattern key (use list_refactor_patterns() to see options).
        repo_path: Absolute path to the indexed repository root.
        function_name: Required only for the 'deprecate-function' pattern.

    Returns:
        A Markdown string containing the full migration blueprint.
    """
    from dev_guardian.agents.refactor_graph import build_refactor_graph

    logger.info("mcp_generate_blueprint", pattern=pattern, repo_path=repo_path)

    try:
        graph = build_refactor_graph()
        pattern_params = {}
        if function_name:
            pattern_params["function_name"] = function_name

        result = graph.invoke(
            {
                "pattern": pattern,
                "pattern_params": pattern_params,
                "repo_path": repo_path,
                "user_clearance": 0,
                "scribe_retry": 0,
                "messages": [],
            }
        )

        blueprint = result.get("blueprint_md", "")
        verdict = result.get("validation_verdict", "unknown")
        messages = result.get("messages", [])

        header = (
            f"<!-- Guardian Self-Healing Blueprint -->\n"
            f"<!-- Pattern: {pattern} | Validation: {verdict} -->\n\n"
        )
        trace = "\n\n---\n## Agent Trace\n" + "\n".join(f"- {m}" for m in messages)

        return header + blueprint + trace

    except Exception as exc:
        logger.error("mcp_generate_blueprint_error", error=str(exc))
        return f"[Guardian Error] Blueprint generation failed: {exc}"


# ── Cluster registration entry ────────────────────────────────────────

CLUSTER_REGISTRY["self_healing"] = {
    "description": (
        "Phase 5.1: Self-Healing Codebase Maintenance. "
        "Deterministic Memgraph blast-radius analysis + Groq-powered migration blueprints."
    ),
    "tools": {
        "list_refactor_patterns": _list_refactor_patterns,
        "analyze_blast_radius": _analyze_blast_radius,
        "generate_refactor_blueprint": _generate_refactor_blueprint,
    },
    "prompts": [],
}
