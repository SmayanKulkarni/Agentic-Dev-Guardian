"""
Phase 5.2 SRE Incident Response StateGraph.

Architecture Blueprint Reference: Phase 5.2 — Automated Incident Response.

Graph topology:
  START → IncidentTriager → SandboxReproducer → HotfixScribe → END
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from dev_guardian.agents.hotfix_scribe import hotfix_scribe_node
from dev_guardian.agents.incident_triager import incident_triager_node
from dev_guardian.agents.sandbox_reproducer import sandbox_reproducer_node
from dev_guardian.agents.state import IncidentState
from dev_guardian.core.logging import get_logger

logger = get_logger(__name__)


def build_sre_graph():
    """
    Build and compile the Phase 5.2 SRE Incident Response StateGraph.

    Returns:
        A compiled LangGraph StateGraph ready for invocation.
    """
    graph = StateGraph(IncidentState)

    graph.add_node("incident_triager", incident_triager_node)
    graph.add_node("sandbox_reproducer", sandbox_reproducer_node)
    graph.add_node("hotfix_scribe", hotfix_scribe_node)

    graph.set_entry_point("incident_triager")
    graph.add_edge("incident_triager", "sandbox_reproducer")
    graph.add_edge("sandbox_reproducer", "hotfix_scribe")
    graph.add_edge("hotfix_scribe", END)

    logger.info("sre_graph_built")
    return graph.compile()
