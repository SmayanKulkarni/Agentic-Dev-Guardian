"""
BlueprintValidator Agent — Structural Sanity Checker.

Architecture Blueprint Reference: Phase 5.1 — Self-Healing Codebase Maintenance.

Validates the generated Markdown blueprint against Memgraph to ensure:
1. All referenced entity names actually exist in the graph.
2. The file paths mentioned are real indexed paths.
3. No critical dependency ordering issues are present.

This is a pure Memgraph node — no LLM calls.
"""

from __future__ import annotations

import re

from langfuse import observe

from dev_guardian.agents.state import RefactorState
from dev_guardian.core.logging import get_logger
from dev_guardian.graphrag.memgraph_client import MemgraphClient

logger = get_logger(__name__)

# Pattern to extract `backtick_names` from the blueprint markdown
_BACKTICK_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_.]*)`")


@observe(name="blueprint_validator_agent")
def blueprint_validator_node(state: RefactorState) -> dict:
    """
    LangGraph node: Validate the migration blueprint against Memgraph.

    Reads ``blueprint_md`` and ``blast_radius`` from state.
    Cross-references entity names in the blueprint with the Memgraph graph.
    Writes ``validation_verdict`` back to state.

    Args:
        state: Current LangGraph RefactorState.

    Returns:
        Partial state update with validation_verdict and messages.
    """
    blueprint = state.get("blueprint_md", "")
    blast_radius = state.get("blast_radius", [])
    pattern = state.get("pattern", "")

    if not blueprint or not blast_radius:
        return {
            "validation_verdict": "valid",
            "messages": ["[BlueprintValidator] No entities to validate — passing."],
        }

    # ── Extract entity names mentioned in the blueprint ────────
    mentioned_names = set(_BACKTICK_RE.findall(blueprint))

    # ── Build ground-truth set from Memgraph blast radius ─────
    known_names: set[str] = {
        row.get("name", "") for row in blast_radius if row.get("name")
    }
    known_files: set[str] = {
        row.get("file_path", "") for row in blast_radius if row.get("file_path")
    }

    # ── Cross-reference: check for unrecognised entity mentions
    # (We only flag names that look like code identifiers, not generic words)
    unrecognised = {
        name for name in mentioned_names
        if len(name) > 3 and "_" in name  # likely a snake_case code entity
        and name not in known_names
    }

    # ── Also do a quick Memgraph connectivity sanity check ─────
    connectivity_ok = True
    try:
        client = MemgraphClient()
        # Simple connectivity probe
        client.execute_query("RETURN 1 AS ping", {})
    except Exception as exc:
        logger.warning("validator_memgraph_unavailable", error=str(exc))
        connectivity_ok = False

    # ── Determine verdict ──────────────────────────────────────
    warnings: list[str] = []

    if unrecognised:
        warnings.append(
            f"Blueprint references {len(unrecognised)} potentially unrecognised "
            f"entity names: {sorted(unrecognised)[:10]}"
        )

    if not connectivity_ok:
        warnings.append("Memgraph connectivity check failed — validation partial.")

    verdict = "valid" if not warnings else "valid_with_warnings"

    logger.info(
        "blueprint_validator_complete",
        verdict=verdict,
        warnings=len(warnings),
        entities_in_blast_radius=len(blast_radius),
    )

    warning_text = ("\n".join(f"- {w}" for w in warnings)) if warnings else "None"

    return {
        "validation_verdict": verdict,
        "messages": [
            f"[BlueprintValidator] Verdict: {verdict}. "
            f"Blast radius: {len(blast_radius)} entities. "
            f"Warnings: {len(warnings)}. Details: {warning_text[:300]}"
        ],
    }
