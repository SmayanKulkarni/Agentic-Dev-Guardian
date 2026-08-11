"""
Proactive codebase audit — rank functions by blast radius, red-team the worst.

Lives here rather than in `cli.py` because two callers need it: the
`dev-guardian audit` command, and the `audit_codebase` MCP tool. The MCP
server talks over stdin/stdout under the stdio transport, so a routine that
prints its progress cannot be shared. Progress is a callback instead, and the
CLI is the only thing that renders it.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from dev_guardian.core.logging import get_logger

logger = get_logger(__name__)

# Fallback span when a graph node carries no end_line, so a function without
# recorded bounds still gets a plausible body to audit rather than one line.
_DEFAULT_SPAN_LINES = 30

_SEVERITY_BADGES = {
    "error": "⚫ ERROR",
    "high": "🔴 HIGH",
    "medium": "🟡 MEDIUM",
    "pass": "🟢 PASS",
}

_RISKIEST_FUNCTIONS_CYPHER = """
MATCH (n:ASTNode)-[:CALLS]->(callee:ASTNode)
WHERE n.node_type IN ["function", "method"]
  AND n.clearance_level <= $cl
  AND n.file_path STARTS WITH $repo_root
RETURN n.name as fn, n.file_path as fp,
       n.start_line as sl, n.end_line as el,
       count(callee) as calls
ORDER BY calls DESC LIMIT $top_n
"""


@dataclass(frozen=True)
class Finding:
    """One audited function and both agents' verdicts on it."""

    rank: int
    name: str
    file: str
    calls: int
    severity: str
    gk_verdict: str
    gk_reason: str
    rt_verdict: str
    rt_reason: str

    @property
    def badge(self) -> str:
        return _SEVERITY_BADGES.get(self.severity, "? UNKNOWN")


@dataclass(frozen=True)
class AuditReport:
    """The full audit: structured findings plus the rendered markdown."""

    repo: str
    scanned: int
    findings: list[Finding]
    markdown: str

    @property
    def counts(self) -> dict[str, int]:
        tally = {"high": 0, "medium": 0, "error": 0, "pass": 0}
        for f in self.findings:
            if f.severity in tally:
                tally[f.severity] += 1
        return tally


def _severity(gk_verdict: str, rt_verdict: str) -> str:
    """Worst of the two verdicts wins."""
    verdicts = {gk_verdict, rt_verdict}
    if "error" in verdicts:
        return "error"
    if "fail" in verdicts:
        return "high"
    if "warn" in verdicts:
        return "medium"
    return "pass"


def _synthetic_diff(rel_path: str, start_line: int, lines: list[str]) -> str:
    """Present an existing function to the agents as if it were newly added.

    The Gatekeeper and Red Team both take a unified diff; an audit has no
    diff, so the function body becomes one.
    """
    header = (
        f"--- /dev/null\n"
        f"+++ b/{rel_path}\n"
        f"@@ -0,0 +{start_line},{len(lines)} @@\n"
    )
    return header + "\n".join(f"+{line}" for line in lines)


def _render_markdown(
    repo: str, scanned: int, findings: list[Finding], counts: dict[str, int]
) -> str:
    sections = [
        f"# 🔍 Guardian Audit Report\n\n"
        f"**Repository**: `{repo}`  \n"
        f"**Scanned**: Top {scanned} highest blast-radius functions  \n\n"
        "---\n",
        f"## Summary\n\n"
        f"| Severity | Count |\n|----------|-------|\n"
        f"| 🔴 High   | {counts['high']} |\n"
        f"| 🟡 Medium | {counts['medium']} |\n"
        f"| ⚫ Error  | {counts['error']} |\n"
        f"| 🟢 Pass   | {counts['pass']} |\n\n---\n",
    ]
    for f in findings:
        sections.append(
            f"## {f.rank}. `{f.name}` — {f.badge}\n\n"
            f"**File**: `{f.file}`  \n"
            f"**Complexity**: {f.calls} function calls  \n\n"
            f"### Gatekeeper: `{f.gk_verdict}`\n{f.gk_reason[:600]}\n\n"
            f"### Red Team: `{f.rt_verdict}`\n{f.rt_reason[:600]}\n\n"
            "---\n"
        )
    return "\n".join(sections)


def run_audit(
    path: Path,
    top: int = 5,
    clearance: int = 0,
    on_progress: Callable[[str], None] | None = None,
) -> AuditReport:
    """Audit the `top` highest blast-radius functions under `path`.

    Queries Kùzu for the functions making the most calls, reads each one
    from disk, and runs it through the Gatekeeper and Red Team agents as a
    synthetic diff.

    Args:
        path: Indexed repository root. Only nodes whose `file_path` starts
            with this are considered.
        top: How many functions to audit, highest call count first.
        clearance: ABAC clearance; nodes above it are invisible.
        on_progress: Called with a human-readable line per function audited.
            The CLI renders these; MCP callers pass nothing.

    Returns:
        An AuditReport. A repository with no indexed call edges yields a
        report with no findings rather than an error.
    """
    from dev_guardian.agents.gatekeeper import gatekeeper_node
    from dev_guardian.agents.red_team import redteam_node
    from dev_guardian.agents.state import GuardianState
    from dev_guardian.graphrag.hybrid_retriever import HybridRetriever
    from dev_guardian.graphrag.kuzu_client import KuzuClient

    def _report(line: str) -> None:
        if on_progress is not None:
            on_progress(line)

    logger.info("audit_start", path=str(path), top=top)

    graph = KuzuClient(data_dir=path)
    risky = graph.execute_query(
        _RISKIEST_FUNCTIONS_CYPHER,
        {"cl": clearance, "repo_root": str(path), "top_n": top},
    )

    if not risky:
        logger.info("audit_no_candidates", path=str(path))
        return AuditReport(
            repo=str(path),
            scanned=top,
            findings=[],
            markdown=(
                f"# 🔍 Guardian Audit Report\n\n**Repository**: `{path}`\n\n"
                "No high-complexity functions found in the graph. "
                "Run `dev-guardian index` on this path first.\n"
            ),
        )

    retriever = HybridRetriever(kuzu=graph, data_dir=path)
    findings: list[Finding] = []

    for rank, row in enumerate(risky, 1):
        fn_name = row["fn"]
        fp = row["fp"]
        start_line = row["sl"] or 1
        end_line = row["el"] or start_line + _DEFAULT_SPAN_LINES
        call_count = row["calls"]
        rel_path = fp.replace(str(path) + "/", "")

        _report(f"[{rank}/{len(risky)}] auditing {fn_name} ({call_count} calls) in {rel_path}")

        try:
            src = Path(fp).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            _report(f"    skipped {rel_path}: {exc}")
            logger.warning("audit_unreadable_file", file=fp, error=str(exc))
            continue

        fn_lines = src[max(0, start_line - 1) : end_line]
        fn_source = "\n".join(fn_lines)

        retriever.jit_embed_nodes([fn_name], clearance)
        rag = retriever.retrieve(query=fn_source[:500], user_clearance=clearance, top_k=5)

        state: GuardianState = {
            "pr_diff": _synthetic_diff(rel_path, start_line, fn_lines),
            "repo_path": str(path),
            "user_clearance": clearance,
            "graphrag_context": rag.get("merged_context", ""),
            "messages": [],
        }

        # gk_result must exist even when the Gatekeeper raises: the Red Team
        # call below merges it into the state either way.
        gk_result: dict = {}
        try:
            gk_result = gatekeeper_node(state)
            gk_report = gk_result.get("gatekeeper_report", {})
            gk_verdict = gk_report.get("verdict", "unknown")
            gk_reason = gk_report.get("reasoning", "")
        except Exception as exc:
            logger.error("audit_gatekeeper_failed", function=fn_name, error=str(exc))
            gk_verdict, gk_reason = "error", str(exc)[:200]

        try:
            rt_report = redteam_node({**state, **gk_result}).get("redteam_report", {})
            rt_verdict = rt_report.get("verdict", "unknown")
            rt_reason = rt_report.get("reasoning", "")
        except Exception as exc:
            logger.error("audit_redteam_failed", function=fn_name, error=str(exc))
            rt_verdict, rt_reason = "error", str(exc)[:200]

        finding = Finding(
            rank=rank,
            name=fn_name,
            file=f"{rel_path} (lines {start_line}–{end_line})",
            calls=call_count,
            severity=_severity(gk_verdict, rt_verdict),
            gk_verdict=gk_verdict,
            gk_reason=gk_reason,
            rt_verdict=rt_verdict,
            rt_reason=rt_reason,
        )
        findings.append(finding)
        _report(f"    {finding.badge}  Gatekeeper={gk_verdict}  RedTeam={rt_verdict}")

    report = AuditReport(
        repo=str(path),
        scanned=len(risky),
        findings=findings,
        markdown="",
    )
    counts = report.counts
    logger.info("audit_complete", **counts)

    return AuditReport(
        repo=report.repo,
        scanned=report.scanned,
        findings=findings,
        markdown=_render_markdown(str(path), len(risky), findings, counts),
    )
