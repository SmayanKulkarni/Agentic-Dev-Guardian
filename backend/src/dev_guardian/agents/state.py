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
from typing import Annotated, Any, TypedDict


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


class RefactorState(TypedDict, total=False):
    """
    State schema for the Phase 5.1 Self-Healing Refactor LangGraph.

    Attributes:
        pattern: Migration pattern key (e.g. "migrate-pydantic-v1-to-v2").
        pattern_params: Optional extra Cypher params for the pattern query.
        repo_path: Path to the indexed repository root.
        user_clearance: ABAC clearance of requesting user.
        blast_radius: Flat list of impacted AST entities from Memgraph.
        refactor_plan: Ordered batch plan produced by RefactorPlanner.
        blueprint_md: Final Markdown migration blueprint from MigrationScribe.
        validation_verdict: "valid" | "valid_with_warnings" from BlueprintValidator.
        scribe_retry: Internal counter to limit MigrationScribe retries.
        messages: Append-only log of agent reasoning traces.
    """

    pattern: str
    pattern_params: dict[str, Any]
    cypher_query: str           # Set by PatternTranslator; used directly by RefactorPlanner
    pattern_description: str    # Human-readable description of the pattern's intent
    repo_path: str
    user_clearance: int
    blast_radius: list[dict[str, Any]]
    refactor_plan: dict[str, Any]
    blueprint_md: str
    validation_verdict: str
    scribe_retry: int
    messages: Annotated[list[str], operator.add]


class IncidentState(TypedDict, total=False):
    """
    State schema for the Phase 5.2 Automated Incident Response LangGraph.

    Attributes:
        stack_trace: Raw stack trace / log input from Sentry/stderr.
        repo_path: Path to the indexed repository root.
        user_clearance: ABAC clearance of requesting user.
        incident_context: Structured triage data from IncidentTriager
                          (failing_function, file, exception, callers).
        reproduction_verdict: "confirmed" | "inconclusive" from SandboxReproducer.
        gatekeeper_report: Gatekeeper's report in incident mode.
        redteam_report: Red Team's report in incident mode.
        hotfix_blueprint: Final Markdown hotfix guide from HotfixScribe.
        messages: Append-only log of agent reasoning traces.
    """

    stack_trace: str
    repo_path: str
    user_clearance: int
    incident_context: dict[str, Any]
    reproduction_verdict: str
    gatekeeper_report: AgentReport
    redteam_report: AgentReport
    hotfix_blueprint: str
    messages: Annotated[list[str], operator.add]
