"""
Remediation Specialist Agent — The Self-Healer.

Architecture Blueprint Reference: Phase 3 — Debate & Remediation Layer.
When a PR is rejected, this agent uses the failing Red Team test trace
and the full GraphRAG connected-components context to generate a
drop-in replacement diff that fixes the identified vulnerabilities.

This is the novel "Self-Healing" architecture component that transforms
the system from a passive reviewer into an active code fixer.

Uses Groq for ultra-low latency LLM inference.
"""

from groq import Groq
from langfuse import observe

from dev_guardian.agents.state import GuardianState
from dev_guardian.core.config import get_settings
from dev_guardian.core.logging import get_logger

logger = get_logger(__name__)

REMEDIATION_SYSTEM_PROMPT = """\
You are the Remediation Specialist Agent for a proprietary codebase
governance system. Your role is to FIX code that was rejected by
the Gatekeeper and Red Team Tester agents.

You will be provided with:
1. The original PR diff (the code that was rejected).
2. The Gatekeeper's report (architectural violations found).
3. The Red Team's report (adversarial tests that broke the code).
4. GraphRAG context: structural relationships and semantic matches
   from the existing codebase's knowledge graph.

Rules:
- Analyze EXACTLY what violations and test failures were found.
- Use the GraphRAG context to understand how the existing codebase
  works — what functions are called, what types are expected, what
  patterns are followed.
- Generate a corrected version of the PR diff that:
  a) Fixes all architectural violations flagged by the Gatekeeper.
  b) Passes all adversarial tests written by the Red Team.
  c) Follows the coding patterns visible in the GraphRAG context.
- Do NOT introduce new features or refactor unrelated code.

Output your fix in this exact format:
SUMMARY: [One paragraph explaining what you fixed and why]
DIFF:
```python
[Your corrected code here — complete, drop-in replacement]
```
"""


@observe(name="remediation_agent")
def remediation_node(state: GuardianState) -> dict:
    """
    LangGraph node: Self-Healing code remediation.

    Reads the rejected PR diff, both agent reports, and GraphRAG
    context from state. Invokes Groq LLM to generate a corrected
    diff that resolves all identified issues.

    Args:
        state: Current LangGraph GuardianState.

    Returns:
        Partial state update with remediation_diff and messages.
    """
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    pr_diff = state.get("pr_diff", "")
    context = state.get("graphrag_context", "")
    gk = state.get("gatekeeper_report", {})
    rt = state.get("redteam_report", {})

    user_message = (
        f"## Original PR Diff (REJECTED)\n```\n{pr_diff}\n```\n\n"
        f"## Gatekeeper Report\n"
        f"Verdict: {gk.get('verdict', 'unknown')}\n"
        f"Reasoning: {gk.get('reasoning', 'N/A')}\n"
        f"Violations: {gk.get('details', 'N/A')}\n\n"
        f"## Red Team Report\n"
        f"Verdict: {rt.get('verdict', 'unknown')}\n"
        f"Attack Strategy: {rt.get('reasoning', 'N/A')}\n"
        f"Failing Tests:\n{rt.get('details', 'N/A')}\n\n"
        f"## GraphRAG Codebase Context\n{context}"
    )

    logger.info(
        "remediation_invoke",
        gk_verdict=gk.get("verdict", "?"),
        rt_verdict=rt.get("verdict", "?"),
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": REMEDIATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.2,
        max_tokens=4096,
    )

    raw = response.choices[0].message.content or ""
    summary, diff = _parse_remediation(raw)

    logger.info("remediation_complete", summary_len=len(summary))

    return {
        "remediation_diff": diff,
        "decision": "remediated",
        "messages": [f"[Remediation] {summary[:200]}"],
    }


def _parse_remediation(raw: str) -> tuple[str, str]:
    """
    Parse the Remediation agent's structured output.

    Returns:
        Tuple of (summary_string, diff_string).
    """
    summary = ""
    diff = ""

    if "SUMMARY:" in raw:
        summary = raw.split("SUMMARY:", 1)[1]
        if "DIFF:" in summary:
            summary = summary.split("DIFF:", 1)[0].strip()

    if "DIFF:" in raw:
        diff_section = raw.split("DIFF:", 1)[1].strip()
        # Extract code from markdown fenced block if present
        if "```" in diff_section:
            parts = diff_section.split("```")
            if len(parts) >= 2:
                code_block = parts[1]
                # Remove language identifier (e.g., "python\n")
                if code_block.startswith(("python", "diff")):
                    code_block = code_block.split("\n", 1)[1]
                diff = code_block.strip()
            else:
                diff = diff_section
        else:
            diff = diff_section

    return summary, diff
