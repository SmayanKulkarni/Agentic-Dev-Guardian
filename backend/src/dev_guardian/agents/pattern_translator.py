"""
PatternTranslator Agent — Natural Language to Memgraph Cypher.

Architecture Blueprint Reference: Phase 5.1 Enhancement — Text-to-Cypher.

This is the FIRST node in the Refactor LangGraph pipeline.
It translates arbitrary natural language refactoring intents into
deterministic Memgraph Cypher queries against the Guardian AST schema.

Decision logic (in order):
  1. If ``pattern`` matches a key in the MIGRATION_PATTERNS registry →
     use the pre-registered Cypher (fast, zero LLM cost, guaranteed correct).
  2. If ``cypher_query`` is already set in state (caller provided raw Cypher) →
     pass through unchanged.
  3. Otherwise → call Groq with the Guardian AST schema to synthesise a query.

This guarantees downstream nodes ALWAYS have a  ``cypher_query`` to execute,
regardless of whether the user typed a pattern key or free-form English.
"""

from __future__ import annotations

from dev_guardian.agents.refactor_patterns import MIGRATION_PATTERNS, get_pattern
from dev_guardian.agents.state import RefactorState
from dev_guardian.core.logging import get_logger
from dev_guardian.core.tracing import observe

logger = get_logger(__name__)


@observe(name="pattern_translator_agent")
def pattern_translator_node(state: RefactorState) -> dict:
    """
    LangGraph node: Translate a pattern to a Memgraph Cypher query.

    Decision tree:
      - Pre-registered key   → return pre-built Cypher (no LLM).
      - Cypher already set   → pass through (advanced user override).
      - Free text            → call Groq to generate Cypher.

    Writes ``cypher_query`` and ``pattern_description`` to state.

    Args:
        state: Current LangGraph RefactorState.

    Returns:
        Partial state update with cypher_query, pattern_description, messages.
    """
    pattern = state.get("pattern", "").strip()
    existing_cypher = state.get("cypher_query", "").strip()

    # ── Fast path 1: raw Cypher already provided ────────────────
    if existing_cypher:
        logger.info("pattern_translator_passthrough", reason="cypher_already_set")
        return {
            "pattern_description": pattern or "Custom Cypher query",
            "messages": ["[PatternTranslator] Custom Cypher query provided — skipping translation."],
        }

    # ── Fast path 2: pre-registered pattern key ─────────────────
    registered = get_pattern(pattern)
    if registered:
        logger.info("pattern_translator_registered", pattern=pattern)
        return {
            "cypher_query": registered["cypher"].strip(),
            "pattern_description": registered["description"],
            "messages": [
                f"[PatternTranslator] Matched registered pattern '{pattern}' "
                f"— using pre-built Cypher (no LLM cost)."
            ],
        }

    # ── Slow path: free-form natural language → Groq Text-to-Cypher
    if not pattern:
        available = list(MIGRATION_PATTERNS.keys())
        return {
            "cypher_query": "",
            "pattern_description": "",
            "messages": [
                f"[PatternTranslator] No pattern provided. "
                f"Use a natural language intent or one of: {available}"
            ],
        }

    logger.info("pattern_translator_llm", pattern=pattern)

    from dev_guardian.harness.skill_router import run_skill
    result = run_skill("pattern_translator", {"pattern": pattern})
    from dev_guardian.harness.schema import PatternCypher
    parsed: PatternCypher = result.parsed  # type: ignore[assignment]
    raw_cypher = parsed.cypher.strip()

    # Strip any accidental markdown fences the LLM might add
    raw_cypher = _strip_fences(raw_cypher)

    # Basic sanity check — must contain MATCH and RETURN
    if "MATCH" not in raw_cypher.upper() or "RETURN" not in raw_cypher.upper():
        logger.warning("pattern_translator_bad_cypher", cypher=raw_cypher[:200])
        return {
            "cypher_query": "",
            "pattern_description": pattern,
            "messages": [
                f"[PatternTranslator] LLM generated an invalid Cypher query "
                f"(missing MATCH/RETURN). Raw: {raw_cypher[:200]}"
            ],
        }

    logger.info(
        "pattern_translator_complete",
        cypher_length=len(raw_cypher),
    )

    return {
        "cypher_query": raw_cypher,
        "pattern_description": pattern,
        "messages": [
            f"[PatternTranslator] Translated '{pattern}' → Cypher query "
            f"({len(raw_cypher)} chars)."
        ],
    }


def _strip_fences(text: str) -> str:
    """Remove markdown code fences the LLM may wrap around the Cypher."""
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()
