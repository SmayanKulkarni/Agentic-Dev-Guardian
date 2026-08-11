"""
MigrationScribe Agent — Blueprint Generator.

Architecture Blueprint Reference: Phase 5.1 — Self-Healing Codebase Maintenance.

Takes the RefactorPlanner's ordered blast-radius batches and uses Groq
to generate a precise, file-by-file Markdown "Master Blueprint" that
the IDE agent (Gemini/Claude) can execute safely.

Guardian provides the analysis; the IDE LLM writes the actual code.
"""

from __future__ import annotations

from dev_guardian.core.logging import get_logger
from dev_guardian.core.tracing import observe

logger = get_logger(__name__)


@observe(name="migration_scribe_agent")
def migration_scribe_node(state: dict) -> dict:
    """
    LangGraph node: Generate the Markdown migration blueprint.

    Reads ``refactor_plan`` from state, fetches supplementary GraphRAG
    context, invokes SkillRouter to write the blueprint, and writes
    ``blueprint_md`` back to state. Migrated to use SkillRouter (Phase 1 harness).

    Args:
        state: Current LangGraph RefactorState.

    Returns:
        Partial state update with blueprint_md and messages.
    """
    plan = state.get("refactor_plan", {})
    pattern = state.get("pattern", "")

    if not plan.get("batches"):
        return {
            "blueprint_md": (
                f"# {pattern} Blueprint\n\n"
                "No entities require migration. Codebase is already compliant."
            ),
            "messages": ["[MigrationScribe] No entities to migrate — skipping blueprint."],
        }

    # ── Fetch GraphRAG context for the impacted area ───────────
    graphrag_context = ""
    try:
        from dev_guardian.graphrag.hybrid_retriever import HybridRetriever
        retriever = HybridRetriever(data_dir=state.get("repo_path") or None)
        result = retriever.retrieve(
            query=f"{pattern} migration {plan.get('description', '')}",
            user_clearance=state.get("user_clearance", 0),
            top_k=8,
        )
        graphrag_context = result.get("merged_context", "")
    except Exception as exc:
        logger.warning("scribe_graphrag_fetch_failed", error=str(exc))

    plan_summary = _summarise_plan(plan)

    logger.info(
        "migration_scribe_invoke",
        pattern=pattern,
        total_entities=plan.get("total_entities", 0),
        batches=plan.get("batch_count", 0),
    )

    from dev_guardian.harness.skill_router import run_skill
    result_skill = run_skill(
        "migration_scribe",
        {
            "pattern": pattern,
            "description": plan.get("description", ""),
            "plan_summary": plan_summary,
            "context": graphrag_context,
        },
    )
    from dev_guardian.harness.schema import MigrationBlueprint
    parsed: MigrationBlueprint = result_skill.parsed  # type: ignore[assignment]
    blueprint = f"## Summary\n{parsed.summary}\n\n{parsed.batches_md}"

    logger.info("migration_scribe_complete", blueprint_length=len(blueprint))
    return {
        "blueprint_md": blueprint,
        "messages": [
            f"[MigrationScribe] Blueprint generated — {len(blueprint)} chars, "
            f"{plan.get('total_entities', 0)} entities across "
            f"{plan.get('batch_count', 0)} batches."
        ],
    }


def _summarise_plan(plan: dict) -> str:
    """Convert the refactor_plan dict into a compact text summary for the LLM."""
    lines = [
        f"- Total entities: {plan.get('total_entities', 0)}",
        f"- Total batches: {plan.get('batch_count', 0)}",
        f"- Batch strategy: {plan.get('batch_strategy', 'by_file')}",
        "",
    ]
    for batch in plan.get("batches", [])[:20]:  # cap at 20 batches for token budget
        lines.append(
            f"Batch {batch['batch_number']}: {batch['file_path']} "
            f"({batch['entity_count']} entities)"
        )
        for entity in batch.get("entities", []):
            lines.append(
                f"  - [{entity.get('node_type', '?')}] "
                f"`{entity.get('name', '?')}` — {entity.get('reason', '')}"
            )
        lines.append("")

    return "\n".join(lines)
