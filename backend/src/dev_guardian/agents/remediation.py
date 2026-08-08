"""
Remediation Specialist Agent — The Self-Healer.

Architecture Blueprint Reference: Phase 3 — Debate & Remediation Layer.
When a PR is rejected, this agent uses the failing Red Team test trace
and the full GraphRAG connected-components context to generate a
drop-in replacement diff that fixes the identified vulnerabilities.

This is the novel "Self-Healing" architecture component that transforms
the system from a passive reviewer into an active code fixer.

Uses Groq for ultra-low latency LLM inference.
"""

from dev_guardian.agents.state import GuardianState
from dev_guardian.core.logging import get_logger
from dev_guardian.core.tracing import observe

logger = get_logger(__name__)


@observe(name="remediation_agent")
def remediation_node(state: GuardianState) -> dict:
    """
    LangGraph node: Self-Healing code remediation.

    Reads the rejected PR diff, both agent reports, and GraphRAG
    context from state. Migrated to use SkillRouter (Phase 1 harness).

    Args:
        state: Current LangGraph GuardianState.

    Returns:
        Partial state update with remediation_diff and messages.
    """
    pr_diff = state.get("pr_diff", "")
    context = state.get("graphrag_context", "")
    gk = state.get("gatekeeper_report", {})
    rt = state.get("redteam_report", {})

    logger.info(
        "remediation_invoke",
        gk_verdict=gk.get("verdict", "?"),
        rt_verdict=rt.get("verdict", "?"),
    )

    from dev_guardian.harness.skill_router import run_skill
    result = run_skill(
        "remediation_specialist",
        {
            "pr_diff": pr_diff,
            "context": context,
            "gk_verdict": gk.get("verdict", "unknown"),
            "gk_reasoning": gk.get("reasoning", "N/A"),
            "gk_details": gk.get("details", "N/A"),
            "rt_verdict": rt.get("verdict", "unknown"),
            "rt_reasoning": rt.get("reasoning", "N/A"),
            "rt_details": rt.get("details", "N/A"),
        },
    )
    from dev_guardian.harness.schema import RemediationResult
    parsed: RemediationResult = result.parsed  # type: ignore[assignment]
    summary = parsed.summary
    diff = parsed.diff

    logger.info("remediation_complete", summary_len=len(summary))
    return {
        "remediation_diff": diff,
        "decision": "remediated",
        "messages": [f"[Remediation] {summary[:200]}"],
    }
