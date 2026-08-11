"""
PR Governance Capability Cluster.

Exposes: evaluate_pr_diff
Domain : "pr_governance"

Loaded JIT when the IDE agent calls equip_capability("pr_governance").
"""

from __future__ import annotations

import json
import subprocess

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
    from dev_guardian.graphrag.clients import get_retriever, reset_clients

    logger.info(
        "mcp_evaluate_diff",
        diff_length=len(diff_content),
        repo_path=repo_path,
    )

    try:
        rag_result = get_retriever().retrieve(
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
        reset_clients()
        logger.error("mcp_evaluate_error", error=str(exc))
        return json.dumps({"error": f"[Guardian Error] PR evaluation failed: {exc}"})


def _raise_github_issue(
    title: str,
    body: str,
    repo_path: str = ".",
    labels: str | None = None,
) -> str:
    """Open a GitHub issue via the `gh` CLI.

    Shells out to `gh issue create` — same convention as Matt Pocock's
    engineering skills use for issue-tracker operations. No GitHub API
    client, no token handling in-process: auth comes from whatever `gh`
    session is already active on the host (`gh auth login`), and the
    target repo is inferred by `gh` from `git remote -v` in `repo_path`.

    Use this tool when a PR evaluation should be escalated to a human —
    e.g. Gatekeeper/Red Team rejected a diff and remediation isn't
    appropriate or has already failed.

    Args:
        title: Issue title.
        body: Issue body (markdown).
        repo_path: Directory of the git clone `gh` should operate in.
        labels: Optional comma-separated label string passed to `--label`.

    Returns:
        A JSON string: `{"issue_url": "<url>"}` on success, or
        `{"error": "[Guardian Error] ..."}` on failure.
    """
    cmd = ["gh", "issue", "create", "--title", title, "--body", body]
    if labels:
        cmd += ["--label", labels]

    logger.info("mcp_raise_github_issue", title=title, repo_path=repo_path)

    try:
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError:
        logger.error("mcp_raise_github_issue_error", error="gh CLI not found")
        return json.dumps(
            {"error": "[Guardian Error] gh CLI not found on PATH"}
        )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        logger.error("mcp_raise_github_issue_error", error=stderr)
        return json.dumps(
            {"error": f"[Guardian Error] gh issue create failed: {stderr}"}
        )

    return json.dumps({"issue_url": result.stdout.strip()})


# ── Cluster registration entry ──────────────────────────────────────

CLUSTER_REGISTRY["pr_governance"] = {
    "description": (
        "Full MoA PR evaluation pipeline: Gatekeeper, Red Team, Supervisor, "
        "and Remediation Specialist agents. Includes GitHub issue escalation."
    ),
    "tools": {
        "evaluate_pr_diff": _evaluate_pr_diff,
        "raise_github_issue": _raise_github_issue,
    },
    "prompts": ["review_pr"],
}
