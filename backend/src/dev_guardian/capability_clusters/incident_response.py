"""
Incident Response Capability Cluster.

Exposes: triage_incident, generate_hotfix_blueprint
Domain : "incident_response"

Loaded JIT when the IDE agent calls equip_capability("incident_response").
"""

from __future__ import annotations

import json

from dev_guardian.capability_clusters.core import CLUSTER_REGISTRY
from dev_guardian.core.logging import get_logger

logger = get_logger(__name__)


# ── Tool implementations ─────────────────────────────────────────────


def _triage_incident(
    stack_trace: str,
    repo_path: str = ".",
) -> str:
    """Parse a production stack trace and identify the failing function via Memgraph.

    Runs only the IncidentTriager node — zero LLM calls, pure regex + graph
    traversal. Returns a structured JSON triage report: failing function,
    exception type, and upstream callers (blast radius for the bug).

    Use this first to understand the scope of a production incident before
    generating a full hotfix blueprint.

    Args:
        stack_trace: Raw Python stack trace string (copy-paste from Sentry,
                     terminal stderr, or any log aggregator).
        repo_path: Absolute path to the indexed repository root.

    Returns:
        JSON with failing_function, exception details, and caller blast radius.
    """
    from dev_guardian.agents.incident_triager import incident_triager_node

    logger.info("mcp_triage_incident", trace_length=len(stack_trace))

    try:
        result = incident_triager_node(
            {
                "stack_trace": stack_trace,
                "repo_path": repo_path,
                "user_clearance": 0,
                "messages": [],
            }
        )
        ctx = result.get("incident_context", {})
        return json.dumps(
            {
                "failing_function": ctx.get("failing_function", ""),
                "failing_file": ctx.get("failing_file", ""),
                "exception_type": ctx.get("exception_type", ""),
                "exception_msg": ctx.get("exception_msg", ""),
                "caller_count": ctx.get("caller_count", 0),
                "callers": [c.get("name") for c in ctx.get("callers", [])[:10]],
                "agent_message": result.get("messages", [""])[0],
            },
            indent=2,
        )
    except Exception as exc:
        return json.dumps({"error": f"Triage failed: {exc}"})


def _generate_hotfix_blueprint(
    stack_trace: str,
    repo_path: str = ".",
) -> str:
    """Run the full SRE incident response pipeline and generate a Markdown hotfix blueprint.

    Executes the 3-agent SRE LangGraph pipeline:
      1. IncidentTriager → pure regex + Memgraph blast-radius mapping.
      2. SandboxReproducer → Gatekeeper + Red Team confirm the bug.
      3. HotfixScribe → targeted Markdown hotfix guide via Groq.

    The hotfix blueprint is scoped to the SINGLE failing function — not the
    whole codebase. Ready to hand to your IDE agent to execute immediately.

    Args:
        stack_trace: Raw Python stack trace string.
        repo_path: Absolute path to the indexed repository root.

    Returns:
        A Markdown string containing the targeted hotfix blueprint.
    """
    from dev_guardian.agents.sre_graph import build_sre_graph

    logger.info("mcp_generate_hotfix", trace_length=len(stack_trace))

    try:
        graph = build_sre_graph()
        result = graph.invoke(
            {
                "stack_trace": stack_trace,
                "repo_path": repo_path,
                "user_clearance": 0,
                "messages": [],
            }
        )

        blueprint = result.get("hotfix_blueprint", "")
        verdict = result.get("reproduction_verdict", "unknown")
        messages = result.get("messages", [])

        header = (
            "<!-- Guardian SRE Hotfix Blueprint -->\n"
            f"<!-- Reproduction: {verdict} -->\n\n"
        )
        trace = "\n\n---\n## Agent Trace\n" + "\n".join(f"- {m}" for m in messages)
        return header + blueprint + trace

    except Exception as exc:
        logger.error("mcp_generate_hotfix_error", error=str(exc))
        return f"[Guardian Error] Hotfix generation failed: {exc}"


# ── Cluster registration ─────────────────────────────────────────────

CLUSTER_REGISTRY["incident_response"] = {
    "description": (
        "Phase 5.2: Automated SRE Incident Response. "
        "Stack trace triage via Memgraph + Gatekeeper/Red Team sandbox reproduction "
        "+ targeted hotfix blueprint generation."
    ),
    "tools": {
        "triage_incident": _triage_incident,
        "generate_hotfix_blueprint": _generate_hotfix_blueprint,
    },
    "prompts": [],
}
