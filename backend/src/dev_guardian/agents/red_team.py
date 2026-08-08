"""
Red Team Tester Agent — Adversarial Test Generator.

Architecture Blueprint Reference: Phase 3 — MoA Execution Layer.
Writes hostile PyTest edge-cases targeting the PR diff to expose
unhandled exceptions, boundary violations, and logic errors.

Runs concurrently with the Gatekeeper in the MoA layer.
Migrated to use SkillRouter (Phase 1 harness).
"""

from dev_guardian.agents.state import GuardianState
from dev_guardian.core.logging import get_logger
from dev_guardian.core.tracing import observe

logger = get_logger(__name__)


@observe(name="redteam_agent")
def redteam_node(state: GuardianState) -> dict:
    """
    LangGraph node: Red Team adversarial testing.

    Reads ``pr_diff`` and ``graphrag_context`` from state,
    routes through SkillRouter (harness) to invoke the LLM,
    and writes the parsed ``redteam_report`` back to state.

    Args:
        state: Current LangGraph GuardianState.

    Returns:
        Partial state update with redteam_report and messages.
    """
    pr_diff = state.get("pr_diff", "")
    context = state.get("graphrag_context", "")

    logger.info("redteam_invoke", diff_len=len(pr_diff))

    from dev_guardian.harness.skill_router import run_skill
    result = run_skill(
        "adversarial_redteam",
        {"pr_diff": pr_diff, "context": context},
    )
    report = result.to_agent_report()

    logger.info("redteam_complete", verdict=report.get("verdict"))
    return {
        "redteam_report": report,
        "messages": [f"[RedTeam] Verdict: {report.get('verdict')}"],
    }
