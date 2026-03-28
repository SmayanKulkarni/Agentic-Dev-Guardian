"""
PR Governance Capability Cluster.

Exposes: evaluate_pr_diff
Domain : "pr_governance"

Loaded JIT when the IDE agent calls equip_capability("pr_governance").
"""

from __future__ import annotations

import json

from dev_guardian.capability_clusters.core import CLUSTER_REGISTRY
from dev_guardian.core.logging import get_logger

logger = get_logger(__name__)

# ── Tool implementations ────────────────────────────────────────────


def _evaluate_pr_diff(
    diff_content: str,
    repo_path: str = ".",
    clearance: int = 0,
) -> str:
    """Evaluate a Pull Request diff using the full MoA agent pipeline.

    Runs the complete Mixture-of-Agents evaluation pipeline:
    1. Retrieves GraphRAG context for the changed code.
    2. Gatekeeper Agent checks for architectural violations.
    3. Red Team Tester Agent generates adversarial test cases.
    4. Supervisor merges reports and routes to debate or remediation.
    5. If rejected, the Remediation Specialist generates a corrected diff.

    Use this tool when a developer submits code changes and you need
    to verify they are safe, architecturally consistent, and well-tested
    before merging.

    Args:
        diff_content: The raw unified diff string (e.g., output of
                      ``git diff`` or a PR diff from GitHub).
        repo_path: Absolute path to the indexed repository root.
        clearance: ABAC security clearance level of the requesting user.

    Returns:
        A JSON string containing the pipeline decision (approve/remediate),
        agent messages, and any remediation diff if applicable.
    """
    from dev_guardian.agents.graph import build_guardian_graph
    from dev_guardian.graphrag.hybrid_retriever import HybridRetriever

    logger.info(
        "mcp_evaluate_diff",
        diff_length=len(diff_content),
        repo_path=repo_path,
    )

    try:
        retriever = HybridRetriever()
        rag_result = retriever.retrieve(
            query=diff_content[:500],
            user_clearance=clearance,
            top_k=10,
        )
        context = rag_result.get("merged_context", "")

        graph = build_guardian_graph()
        result = graph.invoke(
            {
                "pr_diff": diff_content,
                "repo_path": repo_path,
                "user_clearance": clearance,
                "graphrag_context": context,
                "messages": [],
            }
        )

        output = {
            "decision": result.get("decision", "unknown"),
            "messages": result.get("messages", []),
            "remediation_diff": result.get("remediation_diff", ""),
            "gatekeeper_verdict": result.get("gatekeeper_report", {}).get(
                "verdict", ""
            ),
            "redteam_verdict": result.get("redteam_report", {}).get("verdict", ""),
        }
        return json.dumps(output, indent=2)

    except Exception as exc:
        logger.error("mcp_evaluate_error", error=str(exc))
        return json.dumps({"error": f"[Guardian Error] PR evaluation failed: {exc}"})


# ── Cluster registration entry ──────────────────────────────────────

CLUSTER_REGISTRY["pr_governance"] = {
    "description": (
        "Full MoA PR evaluation pipeline: Gatekeeper, Red Team, Supervisor, "
        "and Remediation Specialist agents."
    ),
    "tools": {
        "evaluate_pr_diff": _evaluate_pr_diff,
    },
    "prompts": ["review_pr"],
}
