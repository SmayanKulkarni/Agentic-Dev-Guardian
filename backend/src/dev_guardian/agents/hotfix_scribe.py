"""
HotfixScribe Agent — Targeted Hotfix Blueprint Generator.

Architecture Blueprint Reference: Phase 5.2 — Automated Incident Response.

Unlike MigrationScribe (which covers entire codebases), HotfixScribe
is laser-focused on ONE failing function. It produces a terse, actionable
Markdown hotfix guide that the IDE agent can execute immediately.
"""

from __future__ import annotations

from dev_guardian.agents.state import GuardianState
from dev_guardian.core.logging import get_logger
from dev_guardian.core.tracing import observe

logger = get_logger(__name__)


@observe(name="hotfix_scribe_agent")
def hotfix_scribe_node(state: GuardianState) -> dict:
    """
    LangGraph node: Hotfix blueprint generation.

    Assembles incident context, reproduction verdict, and agent
    reports into a structured Markdown hotfix blueprint.
    Migrated to use SkillRouter (Phase 1 harness).

    Args:
        state: Current LangGraph GuardianState.

    Returns:
        Partial state update with hotfix_blueprint and messages.
    """
    incident = state.get("incident_context", {})
    repro = state.get("repro_result", {})
    gk = state.get("gatekeeper_report", {})
    rt = state.get("redteam_report", {})
    context = state.get("graphrag_context", "")

    failing_func = incident.get("failing_function", "unknown")
    failing_file = incident.get("file_path", "unknown")
    exception_type = incident.get("exception_type", "unknown")
    exception_msg = incident.get("exception_message", "")
    callers = ", ".join(incident.get("callers", []))
    verdict = repro.get("reproduction_verdict", "inconclusive")

    logger.info("hotfix_scribe_invoke", failing_func=failing_func)

    from dev_guardian.harness.skill_router import run_skill
    result = run_skill(
        "hotfix_scribe",
        {
            "failing_func": failing_func,
            "failing_file": failing_file,
            "exception_type": exception_type,
            "exception_msg": exception_msg,
            "callers": callers,
            "verdict": verdict,
            "gk_verdict": gk.get("verdict", "N/A"),
            "gk_reasoning": gk.get("reasoning", "N/A"),
            "gk_details": gk.get("details", "N/A"),
            "rt_verdict": rt.get("verdict", "N/A"),
            "rt_reasoning": rt.get("reasoning", "N/A"),
            "rt_details": rt.get("details", "N/A"),
            "context": context,
        },
    )
    from dev_guardian.harness.schema import HotfixBlueprint
    parsed: HotfixBlueprint = result.parsed  # type: ignore[assignment]
    blueprint_md = (
        f"## Root Cause\n{parsed.root_cause}\n\n"
        f"## Immediate Mitigation\n{parsed.immediate_mitigation}\n\n"
        f"## Full Fix\n{parsed.full_fix}\n\n"
        f"## Verification\n{parsed.verification}"
    )

    logger.info("hotfix_scribe_complete", blueprint_len=len(blueprint_md))
    return {
        "hotfix_blueprint": {
            "failing_function": failing_func,
            "file_path": failing_file,
            "blueprint_md": blueprint_md,
        },
        "messages": [f"[HotfixScribe] Blueprint generated for `{failing_func}`"],
    }
