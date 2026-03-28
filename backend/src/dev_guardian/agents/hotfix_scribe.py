"""
HotfixScribe Agent — Targeted Hotfix Blueprint Generator.

Architecture Blueprint Reference: Phase 5.2 — Automated Incident Response.

Unlike MigrationScribe (which covers entire codebases), HotfixScribe
is laser-focused on ONE failing function. It produces a terse, actionable
Markdown hotfix guide that the IDE agent can execute immediately.
"""

from __future__ import annotations

from groq import Groq
from langfuse import observe

from dev_guardian.agents.state import IncidentState
from dev_guardian.core.config import get_settings
from dev_guardian.core.logging import get_logger
from dev_guardian.graphrag.hybrid_retriever import HybridRetriever

logger = get_logger(__name__)

HOTFIX_SYSTEM_PROMPT = """\
You are the Hotfix Scribe for an autonomous SRE governance system.
A production incident has been detected, triaged, and confirmed by adversarial agents.
Your task: write a concise, file-specific Markdown hotfix guide for the IDE developer agent.

## Rules
1. Focus ONLY on the single failing function — do not rewrite surrounding code.
2. Provide exact structural instructions (parameter guards, exception handling,
   input validation, etc). Do NOT write code — describe what to change and why.
3. Include one "Immediate Mitigation" step that can be done in under 5 minutes.
4. Include a "Root Cause" section (2-3 sentences).
5. Include a "Verification" step: what test to run to confirm the fix worked.
6. Be CONCISE — this is a hotfix, not a refactor. Total length ≤ 400 words.

## Output Format

# 🚨 Hotfix Blueprint: `[function_name]`

## Root Cause
[2-3 sentences]

## Immediate Mitigation (< 5 min)
[Single most impactful structural change]

## Full Fix Instructions
- `[function_name]` in `[file_path]`:
  - [Specific instruction 1]
  - [Specific instruction 2]

## Callers at Risk
[List of functions that call the failing function — these may propagate the bug]

## Verification
[Exact command or assertion to confirm the fix]
"""


@observe(name="hotfix_scribe_agent")
def hotfix_scribe_node(state: IncidentState) -> dict:
    """
    LangGraph node: Generate a targeted Markdown hotfix blueprint.

    Reads ``incident_context``, ``reproduction_verdict``,
    ``gatekeeper_report``, and ``redteam_report`` from state.
    Calls Groq to write a concise, actionable hotfix guide.

    Args:
        state: Current LangGraph IncidentState.

    Returns:
        Partial state update with hotfix_blueprint and messages.
    """
    incident_context = state.get("incident_context", {})
    gk_report = state.get("gatekeeper_report", {})
    rt_report = state.get("redteam_report", {})
    verdict = state.get("reproduction_verdict", "inconclusive")

    if not incident_context:
        return {
            "hotfix_blueprint": "# No incident context available.",
            "messages": ["[HotfixScribe] Skipped — no incident context."],
        }

    failing_func = incident_context.get("failing_function", "unknown")
    logger.info("hotfix_scribe_start", failing_func=failing_func, verdict=verdict)

    # ── Fetch GraphRAG semantic context for the failing function ─
    # Disabled temporarily to bypass Groq 12K TPM limit on 'on_demand' tier
    graphrag_context = ""
    # try:
    #     retriever = HybridRetriever()
    #     result = retriever.retrieve(
    #         query=f"{failing_func} {incident_context.get('exception_type', '')} fix",
    #         user_clearance=state.get("user_clearance", 0),
    #         top_k=2,
    #     )
    #     graphrag_context = result.get("merged_context", "")
    # except Exception as exc:
    #     logger.warning("hotfix_scribe_graphrag_error", error=str(exc))

    # ── Build user message ────────────────────────────────────────
    callers = [c.get("name", "?") for c in incident_context.get("callers", [])[:8]]
    user_msg = (
        f"## Incident Context\n"
        f"- **Failing Function**: `{failing_func}`\n"
        f"- **File**: `{incident_context.get('failing_file', 'unknown')}`\n"
        f"- **Exception**: `{incident_context.get('exception_type', '?')}`: "
        f"{incident_context.get('exception_msg', '')}\n"
        f"- **Reproduction Verdict**: {verdict.upper()}\n"
        f"- **Known Callers**: {', '.join(callers) if callers else 'none'}\n\n"
        f"## Gatekeeper Analysis\n"
        f"Verdict: {gk_report.get('verdict', '?')}\n"
        f"{gk_report.get('reasoning', '')}\n"
        f"{gk_report.get('details', '')}\n\n"
        f"## Red Team Analysis\n"
        f"Verdict: {rt_report.get('verdict', '?')}\n"
        f"{rt_report.get('reasoning', '')}\n"
        f"{rt_report.get('details', '')}\n\n"
        f"## GraphRAG Codebase Context\n{graphrag_context}"
    )

    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": HOTFIX_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.1,
        max_tokens=1024,
    )

    blueprint = (response.choices[0].message.content or "").strip()

    logger.info("hotfix_scribe_complete", blueprint_length=len(blueprint))

    return {
        "hotfix_blueprint": blueprint,
        "messages": [
            f"[HotfixScribe] Hotfix blueprint generated for `{failing_func}` "
            f"({len(blueprint)} chars, verdict: {verdict})."
        ],
    }
