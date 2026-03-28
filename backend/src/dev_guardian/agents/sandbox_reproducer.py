"""
SandboxReproducer Agent — Bug Confirmation via Existing MoA Agents.

Architecture Blueprint Reference: Phase 5.2 — Automated Incident Response.

Reuses the Phase 3 Gatekeeper and Red Team agents in "incident mode":
  - Synthesises a minimal pseudo-diff from the incident context.
  - Runs both agents against this pseudo-diff + GraphRAG context.
  - Writes a ``reproduction_verdict``: "confirmed" | "inconclusive".

This node deliberately reuses Phase 3 agents — no code duplication.
"""

from __future__ import annotations

from langfuse import observe

from dev_guardian.agents.gatekeeper import gatekeeper_node
from dev_guardian.agents.red_team import redteam_node
from dev_guardian.agents.state import AgentReport, GuardianState, IncidentState
from dev_guardian.core.logging import get_logger
from dev_guardian.graphrag.hybrid_retriever import HybridRetriever

logger = get_logger(__name__)


def _build_incident_pseudo_diff(incident_context: dict) -> str:
    """
    Synthesise a minimal pseudo-diff from the incident context.

    The MoA agents expect a diff string. We fabricate a terse one
    that conveys the failing function signature and exception. This
    gives the agents actionable context without needing an actual diff.
    """
    func = incident_context.get("failing_function", "unknown")
    file_path = incident_context.get("failing_file", "unknown")
    exc_type = incident_context.get("exception_type", "UnknownError")
    exc_msg = incident_context.get("exception_msg", "")
    callers = [c.get("name", "?") for c in incident_context.get("callers", [])[:5]]

    return (
        f"# INCIDENT REPORT — Auto-generated pseudo-diff\n"
        f"# Failing function: {func}\n"
        f"# File: {file_path}\n"
        f"# Exception: {exc_type}: {exc_msg}\n"
        f"# Known callers: {', '.join(callers) if callers else 'none found'}\n\n"
        f"--- a/{file_path}\n"
        f"+++ b/{file_path}\n"
        f"@@ production failure in `{func}` @@\n"
        f"-  def {func}(...):\n"
        f"+  # RAISES {exc_type}: {exc_msg}\n"
    )


@observe(name="sandbox_reproducer_agent")
def sandbox_reproducer_node(state: IncidentState) -> dict:
    """
    LangGraph node: Reproduce the bug via existing MoA agents.

    Converts the incident context into a pseudo-diff, fetches GraphRAG
    context for the failing module, then calls gatekeeper_node and
    redteam_node to validate whether the bug is structurally reproducible.

    Args:
        state: Current LangGraph IncidentState.

    Returns:
        Partial state update with gatekeeper_report, redteam_report,
        reproduction_verdict, and messages.
    """
    incident_context = state.get("incident_context", {})
    clearance = state.get("user_clearance", 0)

    if not incident_context:
        return {
            "reproduction_verdict": "inconclusive",
            "messages": ["[SandboxReproducer] No incident context — cannot reproduce."],
        }

    failing_func = incident_context.get("failing_function", "unknown")
    logger.info("sandbox_reproducer_start", failing_func=failing_func)

    # ── Fetch GraphRAG context for the failing module ───────────
    # Disabled temporarily to bypass Groq 12K TPM limit on 'on_demand' tier
    graphrag_context = ""
    # try:
    #     retriever = HybridRetriever()
    #     result = retriever.retrieve(
    #         query=f"{failing_func} {incident_context.get('exception_type', '')}",
    #         user_clearance=clearance,
    #         top_k=2,
    #     )
    #     graphrag_context = result.get("merged_context", "")
    # except Exception as exc:
    #     logger.warning("sandbox_reproducer_graphrag_error", error=str(exc))

    # ── Build a GuardianState-compatible dict for Phase 3 nodes ─
    pseudo_diff = _build_incident_pseudo_diff(incident_context)
    moa_state = GuardianState(
        pr_diff=pseudo_diff,
        repo_path=incident_context.get("repo_path", "."),
        user_clearance=clearance,
        graphrag_context=graphrag_context,
        messages=[],
    )

    # ── Run Gatekeeper ──────────────────────────────────────────
    gk_result = gatekeeper_node(moa_state)
    gk_report: AgentReport = gk_result.get("gatekeeper_report", {})

    # Update state for red_team call (safely merge partial state)
    moa_state_with_gk = moa_state.copy()
    for k, v in gk_result.items():
        if k == "messages":
            moa_state_with_gk["messages"] = moa_state_with_gk.get("messages", []) + v
        else:
            moa_state_with_gk[k] = v  # type: ignore

    # ── Run Red Team ────────────────────────────────────────────
    rt_result = redteam_node(moa_state_with_gk)
    rt_report: AgentReport = rt_result.get("redteam_report", {})

    # ── Determine reproduction verdict ──────────────────────────
    gk_verdict = gk_report.get("verdict", "warn")
    rt_verdict = rt_report.get("verdict", "warn")

    if gk_verdict in ("fail", "warn") or rt_verdict in ("fail", "warn"):
        verdict = "confirmed"
    else:
        verdict = "inconclusive"

    logger.info(
        "sandbox_reproducer_complete",
        verdict=verdict,
        gk=gk_verdict,
        rt=rt_verdict,
    )

    return {
        "gatekeeper_report": gk_report,
        "redteam_report": rt_report,
        "reproduction_verdict": verdict,
        "messages": [
            f"[SandboxReproducer] Bug reproduction verdict: {verdict.upper()}. "
            f"Gatekeeper: {gk_verdict} | Red Team: {rt_verdict}."
        ],
    }
