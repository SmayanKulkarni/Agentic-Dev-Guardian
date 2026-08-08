"""
MoA + Debate + Remediation StateGraph.

Architecture Blueprint Reference: Phase 3 — LangGraph Agent Workflows.
Constructs the complete multi-agent orchestration graph implementing:

1. **MoA Layer**: Gatekeeper and Red Team run in parallel branches.
2. **Supervisor Node**: Merges both reports and makes the decision.
3. **Debate Node**: Resolves contradictions between agents.
4. **Remediation Node**: Self-heals rejected PRs using GraphRAG context.

Graph Topology:
  ┌─────────────┐
  │   START      │
  └──────┬───────┘
         │
  ┌──────▼───────┐
  │  MoA Fan-Out │──────────────────┐
  │  (parallel)  │                  │
  └──────┬───────┘                  │
         │                          │
  ┌──────▼───────┐          ┌───────▼──────┐
  │  Gatekeeper  │          │  Red Team    │
  └──────┬───────┘          └───────┬──────┘
         │                          │
  ┌──────▼──────────────────────────▼──────┐
  │            Supervisor                   │
  │  (merge reports → decide routing)       │
  └──────┬──────────┬──────────────┬───────┘
         │          │              │
      approve     debate       remediate
         │          │              │
         ▼      ┌───▼───┐    ┌────▼─────┐
        END     │ Debate │    │Remediate │
                └───┬───┘    └────┬─────┘
                    │             │
                    ▼             ▼
                   END           END
"""

from langgraph.graph import END, StateGraph

from dev_guardian.agents.gatekeeper import gatekeeper_node
from dev_guardian.agents.red_team import redteam_node
from dev_guardian.agents.remediation import remediation_node
from dev_guardian.agents.state import GuardianState
from dev_guardian.core.logging import get_logger
from dev_guardian.core.tracing import observe

logger = get_logger(__name__)


@observe(name="supervisor_node")
def supervisor_node(state: GuardianState) -> dict:
    """
    Supervisor: merge MoA reports and decide routing.

    Logic:
    - Both PASS → approve
    - Both FAIL → remediate (skip debate, go straight to fix)
    - Disagreement → debate
    - Any WARN + FAIL → remediate
    """
    gk = state.get("gatekeeper_report", {})
    rt = state.get("redteam_report", {})
    gk_v = gk.get("verdict", "warn")
    rt_v = rt.get("verdict", "warn")

    logger.info(
        "supervisor_decide",
        gk_verdict=gk_v,
        rt_verdict=rt_v,
    )

    if gk_v == "pass" and rt_v == "pass":
        decision = "approve"
    elif gk_v == "fail" and rt_v == "fail":
        decision = "remediate"
    elif {gk_v, rt_v} == {"warn", "fail"}:
        decision = "remediate"
    elif gk_v != rt_v:
        decision = "debate"
    else:
        # Both warn
        decision = "remediate"

    return {
        "decision": decision,
        "messages": [f"[Supervisor] GK={gk_v}, RT={rt_v} → {decision}"],
    }


@observe(name="debate_node")
def debate_node(state: GuardianState) -> dict:
    """
    Debate: resolve contradictions between Gatekeeper and Red Team.

    Migrated to use SkillRouter (Phase 1 harness).
    Uses GraphRAG context as ground truth evidence.
    """
    gk = state.get("gatekeeper_report", {})
    rt = state.get("redteam_report", {})
    context = state.get("graphrag_context", "")

    from dev_guardian.harness.skill_router import run_skill
    result = run_skill(
        "debate_mediator",
        {
            "gk_verdict": gk.get("verdict", "?"),
            "gk_reasoning": gk.get("reasoning", "N/A"),
            "rt_verdict": rt.get("verdict", "?"),
            "rt_reasoning": rt.get("reasoning", "N/A"),
            "context": context,
        },
    )
    from dev_guardian.harness.schema import DebateResolution
    parsed: DebateResolution = result.parsed  # type: ignore[assignment]
    decision = parsed.decision
    resolution = parsed.explanation

    logger.info("debate_resolved", decision=decision)
    return {
        "debate_resolution": resolution,
        "decision": decision,
        "messages": [f"[Debate] {resolution[:200]}"],
    }


def _route_after_supervisor(state: GuardianState) -> str:
    """Conditional edge: route based on Supervisor's decision."""
    decision = state.get("decision", "remediate")
    if decision == "approve":
        return "approved"
    elif decision == "debate":
        return "needs_debate"
    else:
        return "needs_remediation"


def _route_after_debate(state: GuardianState) -> str:
    """Conditional edge: route based on Debate resolution."""
    decision = state.get("decision", "remediate")
    if decision == "approve":
        return "approved"
    else:
        return "needs_remediation"


def build_guardian_graph() -> StateGraph:
    """
    Build and compile the complete MoA + Debate + Remediation graph.

    Returns:
        A compiled LangGraph StateGraph ready for invocation.
    """
    graph = StateGraph(GuardianState)

    # ── Register nodes ──────────────────────────────────────
    graph.add_node("gatekeeper", gatekeeper_node)
    graph.add_node("red_team", redteam_node)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("debate", debate_node)
    graph.add_node("remediation", remediation_node)

    # ── Entry point: fan-out to MoA parallel branches ───────
    # LangGraph doesn't have native fan-out, so we chain them.
    # The Gatekeeper runs first, then Red Team, then Supervisor
    # merges both reports. This is sequential but functionally
    # equivalent to MoA since both nodes read the SAME immutable
    # state (pr_diff + graphrag_context) and write to DIFFERENT
    # state keys (gatekeeper_report vs redteam_report).
    graph.set_entry_point("gatekeeper")
    graph.add_edge("gatekeeper", "red_team")
    graph.add_edge("red_team", "supervisor")

    # ── Supervisor routing ──────────────────────────────────
    graph.add_conditional_edges(
        "supervisor",
        _route_after_supervisor,
        {
            "approved": END,
            "needs_debate": "debate",
            "needs_remediation": "remediation",
        },
    )

    # ── Debate routing ──────────────────────────────────────
    graph.add_conditional_edges(
        "debate",
        _route_after_debate,
        {
            "approved": END,
            "needs_remediation": "remediation",
        },
    )

    # ── Remediation always ends ─────────────────────────────
    graph.add_edge("remediation", END)

    logger.info("guardian_graph_built")

    return graph.compile()
