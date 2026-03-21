"""
Gatekeeper Agent — Architectural Violation Detector.

Architecture Blueprint Reference: Phase 3 — MoA Execution Layer.
Reviews incoming PR diffs against the GraphRAG structural context
to detect dependency violations and architectural regressions.

Runs concurrently with the Red Team Tester in the MoA layer.
Uses Groq for ultra-low latency LLM inference.
"""

from groq import Groq
from langfuse import observe

from dev_guardian.agents.state import AgentReport, GuardianState
from dev_guardian.core.config import get_settings
from dev_guardian.core.logging import get_logger

logger = get_logger(__name__)

GATEKEEPER_SYSTEM_PROMPT = """\
You are the Gatekeeper Agent for a proprietary codebase governance system.
Your role is to review a Pull Request diff and determine if it introduces
any architectural violations, dependency regressions, or unsafe patterns.

You will be provided with:
1. The PR diff (code changes).
2. GraphRAG context: structural relationships and semantic matches from
   the existing codebase's knowledge graph and vector database.

Rules:
- If the PR modifies a function, check the GraphRAG context for all
  callers and dependents. Flag if the change could break them.
- Flag any new imports that violate the existing dependency graph.
- Flag any removed functions that are still called by other modules.
- If no violations are found, report a PASS verdict.

Output your analysis in this exact format:
VERDICT: [PASS|FAIL|WARN]
REASONING: [One paragraph explaining your analysis]
DETAILS: [Bullet list of specific violations found, or "None" if clean]
"""


@observe(name="gatekeeper_agent")
def gatekeeper_node(state: GuardianState) -> dict:
    """
    LangGraph node: Gatekeeper architectural review.

    Reads ``pr_diff`` and ``graphrag_context`` from state,
    invokes Groq LLM with the Gatekeeper system prompt,
    and writes the parsed ``gatekeeper_report`` back to state.

    Args:
        state: Current LangGraph GuardianState.

    Returns:
        Partial state update with gatekeeper_report and messages.
    """
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    pr_diff = state.get("pr_diff", "")
    context = state.get("graphrag_context", "")

    user_message = (
        f"## PR Diff\n```\n{pr_diff}\n```\n\n"
        f"## GraphRAG Codebase Context\n{context}"
    )

    logger.info("gatekeeper_invoke", diff_len=len(pr_diff))

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": GATEKEEPER_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.1,
        max_tokens=1024,
    )

    raw = response.choices[0].message.content or ""
    report = _parse_report(raw)

    logger.info(
        "gatekeeper_complete",
        verdict=report["verdict"],
    )

    return {
        "gatekeeper_report": report,
        "messages": [f"[Gatekeeper] Verdict: {report['verdict']}"],
    }


def _parse_report(raw: str) -> AgentReport:
    """Parse structured LLM output into an AgentReport."""
    verdict = "warn"
    reasoning = ""
    details = ""

    for line in raw.split("\n"):
        upper = line.strip().upper()
        if upper.startswith("VERDICT:"):
            v = line.split(":", 1)[1].strip().lower()
            if v in ("pass", "fail", "warn"):
                verdict = v
        elif upper.startswith("REASONING:"):
            reasoning = line.split(":", 1)[1].strip()
        elif upper.startswith("DETAILS:"):
            details = line.split(":", 1)[1].strip()

    # Capture multi-line details after the DETAILS: header
    if "DETAILS:" in raw:
        details_section = raw.split("DETAILS:", 1)[1].strip()
        if details_section:
            details = details_section

    return AgentReport(
        agent_name="gatekeeper",
        verdict=verdict,
        reasoning=reasoning,
        details=details,
    )
