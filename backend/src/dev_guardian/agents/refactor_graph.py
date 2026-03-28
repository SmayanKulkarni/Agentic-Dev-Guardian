"""
Phase 5.1 Self-Healing Refactor StateGraph.

Architecture Blueprint Reference:
    Phase 5.1 — Self-Healing Codebase Maintenance.
    Text-to-Cypher Enhancement — PatternTranslator added as entry point.

Graph topology:
  START → PatternTranslator → RefactorPlanner → MigrationScribe
                                                       ↓
                                                 BlueprintValidator
                                                   /          \\
                                               done         retry_scribe
                                                |              |
                                               END     (back to MigrationScribe)
"""

from __future__ import annotations

from langfuse import observe
from langgraph.graph import END, StateGraph

from dev_guardian.agents.blueprint_validator import blueprint_validator_node
from dev_guardian.agents.migration_scribe import migration_scribe_node
from dev_guardian.agents.pattern_translator import pattern_translator_node
from dev_guardian.agents.refactor_planner import refactor_planner_node
from dev_guardian.agents.state import RefactorState
from dev_guardian.core.logging import get_logger

logger = get_logger(__name__)

MAX_RETRIES = 1


def _route_after_validator(state: RefactorState) -> str:
    """Retry once if validator flags issues; end otherwise."""
    verdict = state.get("validation_verdict", "valid")
    retry_count = state.get("scribe_retry", 0)

    if verdict == "valid" or retry_count >= MAX_RETRIES:
        return "done"
    return "retry_scribe"


@observe(name="scribe_retry_node")
def _increment_retry(state: RefactorState) -> dict:
    """Increment the scribe retry counter before looping back."""
    current = state.get("scribe_retry", 0)
    return {
        "scribe_retry": current + 1,
        "messages": [f"[RefactorGraph] Re-running MigrationScribe (attempt {current + 2})."],
    }


def build_refactor_graph():
    """
    Build and compile the Phase 5.1 + Text-to-Cypher Refactor StateGraph.

    Pipeline:
        PatternTranslator → RefactorPlanner → MigrationScribe
                                                     → BlueprintValidator
                                                          → END (or retry)

    Returns:
        A compiled LangGraph StateGraph ready for invocation.
    """
    graph = StateGraph(RefactorState)

    # ── Register nodes ──────────────────────────────────────────
    graph.add_node("pattern_translator", pattern_translator_node)
    graph.add_node("refactor_planner", refactor_planner_node)
    graph.add_node("migration_scribe", migration_scribe_node)
    graph.add_node("blueprint_validator", blueprint_validator_node)
    graph.add_node("retry_increment", _increment_retry)

    # ── Pipeline: PatternTranslator is now the entry point ──────
    graph.set_entry_point("pattern_translator")
    graph.add_edge("pattern_translator", "refactor_planner")
    graph.add_edge("refactor_planner", "migration_scribe")
    graph.add_edge("migration_scribe", "blueprint_validator")

    # ── Validator routing: done or retry scribe ─────────────────
    graph.add_conditional_edges(
        "blueprint_validator",
        _route_after_validator,
        {
            "done": END,
            "retry_scribe": "retry_increment",
        },
    )

    # ── Retry loop back to MigrationScribe ─────────────────────
    graph.add_edge("retry_increment", "migration_scribe")

    logger.info("refactor_graph_built_with_pattern_translator")
    return graph.compile()
