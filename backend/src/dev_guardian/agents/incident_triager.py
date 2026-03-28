"""
IncidentTriager Agent — SRE Stack Trace Parser & Blame Finder.

Architecture Blueprint Reference: Phase 5.2 — Automated Incident Response.

Pure deterministic node (no LLM):
  1. Regex-parses a raw Python/generic stack trace to extract the
     failing function name, file path, and exception type/message.
  2. Queries Memgraph for the responsible AST node and its callers,
     producing a blast-radius "blame" map for the hotfix agent.
"""

from __future__ import annotations

import re
from pathlib import Path

from langfuse import observe

from dev_guardian.agents.state import IncidentState
from dev_guardian.core.logging import get_logger
from dev_guardian.graphrag.memgraph_client import MemgraphClient

logger = get_logger(__name__)

# ── Stack trace frame regex (Python standard traceback format) ───────
# Matches lines like:  File "/path/to/foo.py", line 42, in some_function
_FRAME_RE = re.compile(
    r'File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>\S+)'
)

# Exception line: "SomeError: message text"
_EXCEPTION_RE = re.compile(
    r'^(?P<exc_type>[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*Error[^:]*|'
    r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*):\s*(?P<exc_msg>.+)$',
    re.MULTILINE,
)


def _parse_stack_trace(trace: str) -> dict:
    """
    Extract structured fields from a raw Python stack trace.

    Returns dict with keys:
        frames, failing_function, failing_file, exception_type, exception_msg
    """
    frames = _FRAME_RE.findall(trace)
    # frames is list of (file, line, func) tuples
    structured = [
        {"file": f, "line": int(l), "function": fn} for f, l, fn in frames
    ]

    # The last user-code frame is typically the one that raised the exception
    # We skip frames from stdlib or site-packages
    failing_func = ""
    failing_file = ""
    for frame in reversed(structured):
        fpath = frame["file"]
        if "site-packages" not in fpath and "<" not in fpath:
            failing_func = frame["function"]
            failing_file = fpath
            break

    # If we couldn't determine, fall back to final frame
    if not failing_func and structured:
        failing_func = structured[-1]["function"]
        failing_file = structured[-1]["file"]

    # Extract exception
    exc_match = _EXCEPTION_RE.search(trace)
    exc_type = exc_match.group("exc_type") if exc_match else "UnknownError"
    exc_msg = exc_match.group("exc_msg").strip() if exc_match else ""

    return {
        "frames": structured,
        "failing_function": failing_func,
        "failing_file": failing_file,
        "exception_type": exc_type,
        "exception_msg": exc_msg,
    }


@observe(name="incident_triager_agent")
def incident_triager_node(state: IncidentState) -> dict:
    """
    LangGraph node: Parse stack trace and map blame via Memgraph.

    Reads ``stack_trace`` and ``repo_path`` from state.
    Writes ``incident_context`` (triage + blame graph data) to state.

    Args:
        state: Current LangGraph IncidentState.

    Returns:
        Partial state update with incident_context and messages.
    """
    stack_trace = state.get("stack_trace", "").strip()
    repo_path = state.get("repo_path", ".")
    clearance = state.get("user_clearance", 0)

    logger.info("incident_triager_start", trace_length=len(stack_trace))

    if not stack_trace:
        return {
            "incident_context": {},
            "messages": ["[IncidentTriager] No stack trace provided."],
        }

    # ── Step 1: Parse the raw trace ────────────────────────────
    parsed = _parse_stack_trace(stack_trace)
    failing_func = parsed["failing_function"]
    failing_file = parsed["failing_file"]

    logger.info(
        "incident_triager_parsed",
        failing_func=failing_func,
        failing_file=failing_file,
        exception=parsed["exception_type"],
    )

    # ── Step 2: Blame analysis via Memgraph ────────────────────
    callers: list[dict] = []
    graph_node: dict = {}

    try:
        client = MemgraphClient()

        # Find the AST node for the failing function
        nodes = client.query_node_by_name(
            name=failing_func, user_clearance=clearance
        )
        graph_node = nodes[0] if nodes else {}

        # Find callers (blast radius) — who calls this function?
        callers = client.query_impact_analysis(
            function_name=failing_func,
            user_clearance=clearance,
            max_depth=2,
        )
    except Exception as exc:
        logger.warning("incident_triager_memgraph_error", error=str(exc))
        # Non-fatal: proceed with parse-only result

    incident_context = {
        **parsed,
        "graph_node": graph_node,
        "callers": callers[:20],                   # cap for token budget
        "caller_count": len(callers),
        "repo_path": repo_path,
    }

    caller_names = [c.get("name", "?") for c in callers[:5]]
    return {
        "incident_context": incident_context,
        "messages": [
            f"[IncidentTriager] Identified failing function: `{failing_func}` "
            f"in {Path(failing_file).name} — "
            f"Exception: {parsed['exception_type']}. "
            f"Blast radius: {len(callers)} callers ({caller_names})."
        ],
    }
