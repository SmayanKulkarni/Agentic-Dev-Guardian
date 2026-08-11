"""Audit orchestration: ranking, severity, and agent failure isolation.

`run_audit` is shared by the `audit` CLI command and the `audit_codebase`
MCP tool, so its contract is: never print, never raise for one bad function,
always return a report.
"""
from __future__ import annotations

import pytest

from dev_guardian.audit import (
    AuditReport,
    Finding,
    _severity,
    _synthetic_diff,
    run_audit,
)

RISKY_ROW = {"fn": "process", "fp": "", "sl": 1, "el": 3, "calls": 12}


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "svc.py").write_text("def process():\n    return 1\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def wire(monkeypatch, repo):
    """Point run_audit's lazily imported collaborators at fakes."""

    def _wire(rows=None, gatekeeper=None, redteam=None):
        import dev_guardian.agents.gatekeeper as gk_mod
        import dev_guardian.agents.red_team as rt_mod
        import dev_guardian.graphrag.hybrid_retriever as hr_mod
        import dev_guardian.graphrag.kuzu_client as graph_mod

        if rows is None:
            rows = [{**RISKY_ROW, "fp": str(repo / "svc.py")}]

        class FakeKuzu:
            def __init__(self, data_dir=None) -> None:
                pass

            def execute_query(self, _query, _params):
                return rows

        class FakeRetriever:
            def __init__(self, *_a, **_kw):
                pass

            def jit_embed_nodes(self, *_a, **_kw):
                return None

            def retrieve(self, **_kw):
                return {"merged_context": "ctx"}

        def default_gk(_state):
            return {"gatekeeper_report": {"verdict": "pass", "reasoning": "fine"}}

        def default_rt(_state):
            return {"redteam_report": {"verdict": "pass", "reasoning": "fine"}}

        monkeypatch.setattr(graph_mod, "KuzuClient", FakeKuzu)
        monkeypatch.setattr(hr_mod, "HybridRetriever", FakeRetriever)
        monkeypatch.setattr(gk_mod, "gatekeeper_node", gatekeeper or default_gk)
        monkeypatch.setattr(rt_mod, "redteam_node", redteam or default_rt)

    return _wire


# ── Pure helpers ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("gk", "rt", "expected"),
    [
        ("pass", "pass", "pass"),
        ("warn", "pass", "medium"),
        ("pass", "fail", "high"),
        ("warn", "fail", "high"),
        ("error", "pass", "error"),
        ("fail", "error", "error"),
    ],
)
def test_severity_takes_the_worse_of_the_two_verdicts(gk, rt, expected):
    assert _severity(gk, rt) == expected


def test_synthetic_diff_marks_every_line_as_an_addition():
    diff = _synthetic_diff("svc.py", 10, ["def f():", "    pass"])

    assert "+++ b/svc.py" in diff
    assert "@@ -0,0 +10,2 @@" in diff
    assert diff.endswith("+def f():\n+    pass")


def test_counts_tally_by_severity():
    def finding(rank, severity):
        return Finding(rank, "f", "a.py", 1, severity, "", "", "", "")

    report = AuditReport(
        repo="/r",
        scanned=3,
        findings=[finding(1, "high"), finding(2, "high"), finding(3, "pass")],
        markdown="",
    )

    assert report.counts == {"high": 2, "medium": 0, "error": 0, "pass": 1}


# ── Orchestration ────────────────────────────────────────────────────────────


def test_audit_reports_findings_and_renders_markdown(repo, wire):
    wire()

    report = run_audit(path=repo, top=1)

    assert [f.name for f in report.findings] == ["process"]
    assert report.counts["pass"] == 1
    assert "Guardian Audit Report" in report.markdown
    assert "`process`" in report.markdown


def test_audit_survives_a_gatekeeper_that_raises(repo, wire):
    """Regression: the Red Team call merged an unbound gk_result, so one
    Gatekeeper exception aborted the whole audit with a NameError."""

    def exploding_gatekeeper(_state):
        raise RuntimeError("provider 503")

    wire(gatekeeper=exploding_gatekeeper)

    report = run_audit(path=repo, top=1)

    assert report.counts["error"] == 1
    assert report.findings[0].gk_verdict == "error"
    assert "provider 503" in report.findings[0].gk_reason
    # The Red Team still ran on the surviving state.
    assert report.findings[0].rt_verdict == "pass"


def test_audit_survives_a_red_team_that_raises(repo, wire):
    def exploding_redteam(_state):
        raise RuntimeError("rate limited")

    wire(redteam=exploding_redteam)

    report = run_audit(path=repo, top=1)

    assert report.findings[0].severity == "error"
    assert report.findings[0].gk_verdict == "pass"


def test_audit_skips_functions_whose_file_is_gone(repo, wire):
    wire(rows=[{**RISKY_ROW, "fp": str(repo / "deleted.py")}])

    report = run_audit(path=repo, top=1)

    assert report.findings == []


def test_audit_on_an_unindexed_repo_returns_an_empty_report_not_an_error(repo, wire):
    wire(rows=[])

    report = run_audit(path=repo, top=5)

    assert report.findings == []
    assert "dev-guardian index" in report.markdown


def test_audit_never_writes_to_stdout(repo, wire, capsys):
    """The MCP stdio transport shares the process stdout with the protocol."""
    wire()

    run_audit(path=repo, top=1)

    assert capsys.readouterr().out == ""


def test_progress_callback_receives_a_line_per_function(repo, wire):
    wire()
    seen: list[str] = []

    run_audit(path=repo, top=1, on_progress=seen.append)

    assert any("process" in line for line in seen)
