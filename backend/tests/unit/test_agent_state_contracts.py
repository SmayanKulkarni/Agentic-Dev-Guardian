"""
Agent state contract tests.

Verifies that every agent node function's returned report dict:
  1. Is a dict
  2. Contains a 'verdict' key valid in {"pass", "fail", "warn"}

The GUARDIAN_USE_HARNESS=0 legacy path was removed (see
.scratch/ship-guardian/issues/04-provider-selection-contract.md) — every
agent now routes through SkillRouter unconditionally, so this file only
tests the report-shape contract that survives that migration.
"""
from __future__ import annotations

VALID_VERDICTS = {"pass", "fail", "warn"}

VALID_AGENT_REPORT_KEYS = {"agent_name", "verdict", "reasoning", "details"}


def _assert_agent_report(report: dict, agent_name: str) -> None:
    assert isinstance(report, dict), f"{agent_name}: expected dict, got {type(report)}"
    assert "verdict" in report, f"{agent_name}: missing 'verdict'"
    assert report["verdict"] in VALID_VERDICTS, (
        f"{agent_name}: verdict '{report['verdict']}' not in {VALID_VERDICTS}"
    )


# ── GuardianState field types ─────────────────────────────────────────────────

class TestGuardianStateTypes:
    """Verify GuardianState TypedDict field expectations via the schema module."""

    def test_agent_report_has_required_keys(self):
        report = {"agent_name": "gatekeeper", "verdict": "pass", "reasoning": "ok", "details": ""}
        _assert_agent_report(report, "gatekeeper")

    def test_verdict_values_are_exactly_three(self):
        assert VALID_VERDICTS == {"pass", "fail", "warn"}

    def test_all_verdicts_accepted(self):
        for verdict in ("pass", "fail", "warn"):
            report = {"agent_name": "x", "verdict": verdict, "reasoning": "r" * 10, "details": ""}
            _assert_agent_report(report, "x")

    def test_invalid_verdicts_detected(self):
        import pytest
        for bad_verdict in ("PASS", "approve", "reject", "", None, 1):
            report = {"agent_name": "x", "verdict": bad_verdict}
            with pytest.raises(AssertionError):
                _assert_agent_report(report, "x")
