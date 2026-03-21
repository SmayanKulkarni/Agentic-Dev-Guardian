"""
Red Team Tester Agent — Adversarial Test Generator.

Architecture Blueprint Reference: Phase 3 — MoA Execution Layer.
Writes hostile PyTest edge-cases targeting the PR diff to expose
unhandled exceptions, boundary violations, and logic errors.

Runs concurrently with the Gatekeeper in the MoA layer.
Uses Groq for ultra-low latency LLM inference.
"""

from groq import Groq
from langfuse import observe

from dev_guardian.agents.state import AgentReport, GuardianState
from dev_guardian.core.config import get_settings
from dev_guardian.core.logging import get_logger

logger = get_logger(__name__)

REDTEAM_SYSTEM_PROMPT = """\
You are the Red Team Tester Agent for a proprietary codebase governance system.
Your role is to write adversarial PyTest test cases that attempt to BREAK
the code introduced in a Pull Request diff.

You will be provided with:
1. The PR diff (code changes).
2. GraphRAG context: structural relationships and semantic matches from
   the existing codebase's knowledge graph.

Rules:
- Write 2-4 targeted PyTest test functions that exploit edge cases.
- Focus on: null inputs, type mismatches, boundary values, missing
  error handling, race conditions, and dependency violations.
- Use the GraphRAG context to understand what functions the PR code
  calls, and test if those dependencies are handled correctly.
- If you believe the code is robust and cannot be broken, report PASS.

Output your analysis in this exact format:
VERDICT: [PASS|FAIL|WARN]
REASONING: [One paragraph on your attack strategy and findings]
DETAILS: [The actual PyTest code you wrote, or "No exploits found"]
"""


@observe(name="redteam_agent")
def redteam_node(state: GuardianState) -> dict:
    """
    LangGraph node: Red Team adversarial testing.

    Reads ``pr_diff`` and ``graphrag_context`` from state,
    invokes Groq LLM with the Red Team system prompt,
    and writes the parsed ``redteam_report`` back to state.

    Args:
        state: Current LangGraph GuardianState.

    Returns:
        Partial state update with redteam_report and messages.
    """
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    pr_diff = state.get("pr_diff", "")
    context = state.get("graphrag_context", "")

    user_message = (
        f"## PR Diff\n```\n{pr_diff}\n```\n\n"
        f"## GraphRAG Codebase Context\n{context}"
    )

    logger.info("redteam_invoke", diff_len=len(pr_diff))

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": REDTEAM_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.3,
        max_tokens=2048,
    )

    raw = response.choices[0].message.content or ""
    report = _parse_report(raw)

    logger.info(
        "redteam_complete",
        verdict=report["verdict"],
    )

    return {
        "redteam_report": report,
        "messages": [f"[RedTeam] Verdict: {report['verdict']}"],
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

    # Capture the full test code block after DETAILS:
    if "DETAILS:" in raw:
        details_section = raw.split("DETAILS:", 1)[1].strip()
        if details_section:
            details = details_section

    return AgentReport(
        agent_name="red_team",
        verdict=verdict,
        reasoning=reasoning,
        details=details,
    )
