"""
LangGraph Workflow State Schema.

Architecture Blueprint Reference: Phase 3 — LangGraph Agent Workflows.
Defines the TypedDict that flows through every node in the
MoA + Debate + Remediation StateGraph.

Key Design Decisions:
  - Uses ``Annotated[list, operator.add]`` for message fields
    so that each node APPENDS to the list rather than overwriting.
  - Includes ``decision`` and ``remediation_diff`` for the
    Supervisor's final routing and the Self-Healer's output.
"""

import operator
from typing import Annotated, TypedDict


class AgentReport(TypedDict, total=False):
    """Individual report from a specialist agent."""

    agent_name: str
    verdict: str  # "pass" | "fail" | "warn"
    reasoning: str
    details: str  # structured evidence (test output, violations)


class GuardianState(TypedDict, total=False):
    """
    Central state flowing through the LangGraph StateGraph.

    Attributes:
        pr_diff: The raw Pull Request diff string to evaluate.
        repo_path: Path to the indexed repository root.
        user_clearance: ABAC clearance level of the requesting user.
        graphrag_context: Merged context from HybridRetriever.
        gatekeeper_report: Gatekeeper's architectural analysis.
        redteam_report: Red Team Tester's adversarial test results.
        debate_resolution: Consensus after Gatekeeper/Red Team debate.
        decision: Final verdict — "approve" | "reject" | "remediate".
        remediation_diff: Self-Healer's suggested fix diff.
        messages: Append-only log of agent reasoning traces.
    """

    pr_diff: str
    repo_path: str
    user_clearance: int
    graphrag_context: str
    gatekeeper_report: AgentReport
    redteam_report: AgentReport
    debate_resolution: str
    decision: str
    remediation_diff: str
    messages: Annotated[list[str], operator.add]
