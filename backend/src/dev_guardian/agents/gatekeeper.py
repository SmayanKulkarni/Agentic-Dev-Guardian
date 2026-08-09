"""
Gatekeeper Agent — Architectural Violation Detector.

Architecture Blueprint Reference: Phase 3 — MoA Execution Layer.
Reviews incoming PR diffs against the GraphRAG structural context
to detect dependency violations and architectural regressions.

Runs concurrently with the Red Team Tester in the MoA layer.
Migrated to use SkillRouter (Phase 1 harness).
"""

from dev_guardian.agents.state import GuardianState
from dev_guardian.core.logging import get_logger
from dev_guardian.core.tracing import observe

logger = get_logger(__name__)


@observe(name="gatekeeper_agent")
def gatekeeper_node(state: GuardianState) -> dict:
    """
    LangGraph node: Gatekeeper architectural review.

    Reads ``pr_diff`` and ``graphrag_context`` from state,
    routes through SkillRouter (harness) to invoke the LLM,
    and writes the parsed ``gatekeeper_report`` back to state.

    Args:
        state: Current LangGraph GuardianState.

    Returns:
        Partial state update with gatekeeper_report and messages.
    """
    pr_diff = state.get("pr_diff", "")
    context = state.get("graphrag_context", "")

    logger.info("gatekeeper_invoke", diff_len=len(pr_diff))

    from dev_guardian.harness.skill_router import run_skill
    result = run_skill(
        "architectural_gatekeeper",
        {"pr_diff": pr_diff, "context": context},
    )
    report = result.to_agent_report()

    logger.info("gatekeeper_complete", verdict=report.get("verdict"))
    return {
        "gatekeeper_report": report,
        "messages": [f"[Gatekeeper] Verdict: {report.get('verdict')}"],
    }
