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

from groq import Groq
from langfuse import observe
from langgraph.graph import END, StateGraph

from dev_guardian.agents.gatekeeper import gatekeeper_node
from dev_guardian.agents.red_team import redteam_node
from dev_guardian.agents.remediation import remediation_node
from dev_guardian.agents.state import GuardianState
from dev_guardian.core.config import get_settings
from dev_guardian.core.logging import get_logger

logger = get_logger(__name__)

DEBATE_SYSTEM_PROMPT = """\
You are the Debate Mediator for a codebase governance system.
Two specialist agents disagree on a Pull Request:

- The Gatekeeper says: {gk_verdict} — {gk_reasoning}
- The Red Team says: {rt_verdict} — {rt_reasoning}

Using the GraphRAG codebase context below, determine which agent
is correct. Resolve the contradiction with mathematical precision.

GraphRAG Context:
{context}

Output exactly one line:
RESOLUTION: [APPROVE|REJECT|REMEDIATE] — [One sentence explanation]
"""


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
    elif gk_v != rt_v:
        decision = "debate"
    else:
        # Both warn, or warn+fail combo
        decision = "remediate"

    return {
        "decision": decision,
        "messages": [f"[Supervisor] GK={gk_v}, RT={rt_v} → {decision}"],
    }


@observe(name="debate_node")
def debate_node(state: GuardianState) -> dict:
    """
    Debate: resolve contradictions between Gatekeeper and Red Team.

    Uses Groq LLM to mathematically mediate the disagreement
    using GraphRAG context as ground truth evidence.
    """
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    gk = state.get("gatekeeper_report", {})
    rt = state.get("redteam_report", {})
    context = state.get("graphrag_context", "")

    prompt = DEBATE_SYSTEM_PROMPT.format(
        gk_verdict=gk.get("verdict", "?"),
        gk_reasoning=gk.get("reasoning", "N/A"),
        rt_verdict=rt.get("verdict", "?"),
        rt_reasoning=rt.get("reasoning", "N/A"),
        context=context,
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=256,
    )

    raw = response.choices[0].message.content or ""
    resolution = raw.strip()

    # Parse the resolution into a decision
    decision = "remediate"  # default to safe option
    upper = resolution.upper()
    if "APPROVE" in upper:
        decision = "approve"
    elif "REJECT" in upper or "REMEDIATE" in upper:
        decision = "remediate"

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
