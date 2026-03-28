"""
RefactorPlanner Agent — Blast Radius Analyst.

Architecture Blueprint Reference: Phase 5.1 + Text-to-Cypher Enhancement.

Executes the ``cypher_query`` from state (set by PatternTranslator) against
Memgraph to produce a deterministic, ordered list of impacted AST entities.

This node is now fully decoupled from the pattern registry — it only cares
about the Cypher query that PatternTranslator resolved for it.
No LLM is used here — this is pure graph mathematics.
"""

from __future__ import annotations

from langfuse import observe

from dev_guardian.agents.state import RefactorState
from dev_guardian.core.logging import get_logger
from dev_guardian.graphrag.memgraph_client import MemgraphClient

logger = get_logger(__name__)


@observe(name="refactor_planner_agent")
def refactor_planner_node(state: RefactorState) -> dict:
    """
    LangGraph node: Deterministic blast-radius analysis.

    Reads ``cypher_query``, ``pattern``, and ``repo_path`` from state
    (populated by PatternTranslator), executes the Cypher against Memgraph,
    and writes ``blast_radius`` and ``refactor_plan`` back to state.

    Args:
        state: Current LangGraph RefactorState.

    Returns:
        Partial state update with blast_radius, refactor_plan, messages.
    """
    cypher_query = state.get("cypher_query", "").strip()
    pattern = state.get("pattern", "unknown")
    pattern_description = state.get("pattern_description", pattern)
    repo_path = state.get("repo_path", ".")
    extra_params = state.get("pattern_params", {})

    logger.info("refactor_planner_start", pattern=pattern, has_cypher=bool(cypher_query))

    # ── Guard: abort if no Cypher was produced ─────────────────
    if not cypher_query:
        return {
            "blast_radius": [],
            "refactor_plan": {},
            "messages": [
                "[RefactorPlanner] No Cypher query available — "
                "PatternTranslator may have failed. Cannot run blast-radius analysis."
            ],
        }

    # ── Execute Cypher query against Memgraph ──────────────────
    try:
        client = MemgraphClient()
        params = {"repo_path": repo_path, **extra_params}
        rows = client.execute_query(cypher_query, params)
    except Exception as exc:
        logger.error("refactor_planner_graph_error", error=str(exc))
        return {
            "blast_radius": [],
            "refactor_plan": {},
            "messages": [f"[RefactorPlanner] Memgraph query failed: {exc}"],
        }

    if not rows:
        return {
            "blast_radius": [],
            "refactor_plan": {"batches": [], "total_entities": 0},
            "messages": [
                f"[RefactorPlanner] No entities matched '{pattern}'. "
                "Codebase may already be compliant or the codebase has not been indexed."
            ],
        }

    # ── Group results into ordered batches by file ─────────────
    batches = _build_batches(rows)

    plan = {
        "pattern": pattern,
        "description": pattern_description,
        "total_entities": len(rows),
        "batch_count": len(batches),
        "batch_strategy": "by_file",
        "batches": batches,
    }

    logger.info(
        "refactor_planner_complete",
        pattern=pattern,
        total_entities=len(rows),
        batches=len(batches),
    )

    return {
        "blast_radius": rows,
        "refactor_plan": plan,
        "messages": [
            f"[RefactorPlanner] Found {len(rows)} impacted entities across "
            f"{len(batches)} files for pattern '{pattern}'."
        ],
    }


def _build_batches(rows: list[dict]) -> list[dict]:
    """Group impacted entities into one batch per unique file path."""
    file_map: dict[str, list[dict]] = {}
    for row in rows:
        fp = row.get("file_path", "unknown")
        file_map.setdefault(fp, []).append(row)

    return [
        {
            "batch_number": i,
            "file_path": fp,
            "entities": entities,
            "entity_count": len(entities),
        }
        for i, (fp, entities) in enumerate(file_map.items(), start=1)
    ]
