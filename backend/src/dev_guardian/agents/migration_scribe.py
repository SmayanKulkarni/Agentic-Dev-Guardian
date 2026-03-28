"""
MigrationScribe Agent — Blueprint Generator.

Architecture Blueprint Reference: Phase 5.1 — Self-Healing Codebase Maintenance.

Takes the RefactorPlanner's ordered blast-radius batches and uses Groq
to generate a precise, file-by-file Markdown "Master Blueprint" that
the IDE agent (Gemini/Claude) can execute safely.

Guardian provides the analysis; the IDE LLM writes the actual code.
"""

from __future__ import annotations

from groq import Groq
from langfuse import observe

from dev_guardian.agents.state import RefactorState
from dev_guardian.core.config import get_settings
from dev_guardian.core.logging import get_logger
from dev_guardian.graphrag.hybrid_retriever import HybridRetriever

logger = get_logger(__name__)

SCRIBE_SYSTEM_PROMPT = """\
You are the Migration Scribe for an autonomous software governance system.
You have been given a deterministic refactoring plan produced by graph analysis.
Your task is to generate a precise, developer-facing Markdown migration blueprint.

## Rules
1. For each file listed, provide EXACT migration instructions — be specific about
   which function/class to change and exactly what needs to change structurally.
2. Use the GraphRAG context to make instructions codebase-specific (not generic).
3. Do NOT write code yourself. Describe WHAT needs to change and WHY.
   The developer's IDE agent will write the actual code from your instructions.
4. Include a "Verification" step for each file (e.g. "Run pytest tests/test_auth.py").
5. Order the batches correctly — leaf nodes (deepest dependencies) first.

## Output Format
# [Pattern Name] Migration Blueprint

## Summary
[2-sentence overview]

## Migration Batches

### Batch N: `[file_path]`
**Entities to migrate:** [count]
**Entities:**
- `[entity_name]` ([entity_type]): [Exact instruction]

**Verification:** [What to run to confirm this batch is correct]

---
"""


@observe(name="migration_scribe_agent")
def migration_scribe_node(state: RefactorState) -> dict:
    """
    LangGraph node: Generate the Markdown migration blueprint.

    Reads ``refactor_plan`` from state, fetches supplementary GraphRAG
    context, invokes Groq to write the blueprint, and writes
    ``blueprint_md`` back to state.

    Args:
        state: Current LangGraph RefactorState.

    Returns:
        Partial state update with blueprint_md and messages.
    """
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    plan = state.get("refactor_plan", {})
    pattern = state.get("pattern", "")
    blast_radius = state.get("blast_radius", [])

    if not plan.get("batches"):
        return {
            "blueprint_md": (
                f"# {pattern} Blueprint\n\n"
                "✅ No entities require migration. Codebase is already compliant."
            ),
            "messages": ["[MigrationScribe] No entities to migrate — skipping blueprint."],
        }

    # ── Fetch GraphRAG context for the impacted area ───────────
    graphrag_context = ""
    try:
        retriever = HybridRetriever()
        result = retriever.retrieve(
            query=f"{pattern} migration {plan.get('description', '')}",
            user_clearance=state.get("user_clearance", 0),
            top_k=8,
        )
        graphrag_context = result.get("merged_context", "")
    except Exception as exc:
        logger.warning("scribe_graphrag_fetch_failed", error=str(exc))

    # ── Build the user message ─────────────────────────────────
    plan_summary = _summarise_plan(plan)

    user_message = (
        f"## Migration Pattern\n{pattern}\n\n"
        f"## Pattern Description\n{plan.get('description', '')}\n\n"
        f"## Refactoring Plan (from Memgraph graph analysis)\n{plan_summary}\n\n"
        f"## GraphRAG Codebase Context\n{graphrag_context}"
    )

    logger.info(
        "migration_scribe_invoke",
        pattern=pattern,
        total_entities=plan.get("total_entities", 0),
        batches=plan.get("batch_count", 0),
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SCRIBE_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.2,
        max_tokens=4096,
    )

    blueprint = response.choices[0].message.content or ""

    logger.info(
        "migration_scribe_complete",
        blueprint_length=len(blueprint),
    )

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
