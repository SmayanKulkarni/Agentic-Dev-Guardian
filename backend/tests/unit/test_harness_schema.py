"""
Phase 0+1 — Unit tests for harness schema parsers.

These tests verify the Pydantic schema parsers produce correct output
from realistic LLM responses. They replace the regex-based _parse_report
tests as the canonical regression baseline for the harness path.
"""
from __future__ import annotations

import pytest

from dev_guardian.harness.schema import (
    parse_debate,
    parse_gatekeeper,
    parse_redteam,
    parse_remediation,
)


class TestParseGatekeeper:
    def test_pass_verdict(self):
        raw = "VERDICT: PASS\nREASONING: Clean diff, no violations.\nDETAILS: None"
        r = parse_gatekeeper(raw)
        assert r.verdict == "pass"
        assert "Clean diff" in r.reasoning
        assert r.violations == []

    def test_fail_with_violations(self):
        raw = (
            "VERDICT: FAIL\n"
            "REASONING: Missing auth check.\n"
            "DETAILS:\n- Removed `auth_check` still called\n- Import of `os` violates policy"
        )
        r = parse_gatekeeper(raw)
        assert r.verdict == "fail"
        assert len(r.violations) == 2
        assert any("auth_check" in v for v in r.violations)

    def test_warn_verdict(self):
        raw = "VERDICT: WARN\nREASONING: Minor type concern.\nDETAILS: None"
        r = parse_gatekeeper(raw)
        assert r.verdict == "warn"

    def test_empty_raw_defaults_to_warn(self):
        r = parse_gatekeeper("")
        assert r.verdict == "warn"

    def test_case_insensitive(self):
        raw = "VERDICT: Pass\nREASONING: Looks okay to me.\nDETAILS: None"
        assert parse_gatekeeper(raw).verdict == "pass"


class TestParseRedTeam:
    def test_pass_no_exploits(self):
        raw = "VERDICT: PASS\nREASONING: Code is robust.\nDETAILS: No exploits found"
        r = parse_redteam(raw)
        assert r.verdict == "pass"
        assert r.pytest_code == ""

    def test_fail_with_pytest(self):
        raw = (
            "VERDICT: FAIL\nREASONING: Found null deref.\n"
            "DETAILS:\ndef test_null():\n    assert func(None) == ''"
        )
        r = parse_redteam(raw)
        assert r.verdict == "fail"
        assert "def test_null" in r.pytest_code

    def test_warn_verdict(self):
        raw = "VERDICT: WARN\nREASONING: Possible issue.\nDETAILS: None"
        assert parse_redteam(raw).verdict == "warn"


class TestParseDebate:
    def test_approve_resolution(self):
        raw = "RESOLUTION: APPROVE — Both agents agree the PR is safe."
        r = parse_debate(raw)
        assert r.decision == "approve"
        assert len(r.explanation) > 0

    def test_reject_resolution(self):
        raw = "RESOLUTION: REJECT — Critical security violation found."
        r = parse_debate(raw)
        assert r.decision == "reject"

    def test_remediate_resolution(self):
        raw = "RESOLUTION: REMEDIATE — Agents disagree, fix required."
        r = parse_debate(raw)
        assert r.decision == "remediate"

    def test_default_to_remediate(self):
        r = parse_debate("conflicting outputs detected")
        assert r.decision == "remediate"


class TestParseRemediation:
    def test_summary_and_diff(self):
        raw = (
            "SUMMARY: Fixed the null pointer by adding a guard clause.\n"
            "DIFF:\n```python\ndef func(x):\n    if x is None:\n        return ''\n```"
        )
        r = parse_remediation(raw)
        assert "null pointer" in r.summary
        assert "def func" in r.diff
        assert "```" not in r.diff

    def test_empty_raw(self):
        r = parse_remediation("")
        assert r.summary == ""

    def test_diff_without_fences(self):
        raw = "SUMMARY: Quick fix\nDIFF:\ndef foo(): pass"
        r = parse_remediation(raw)
        assert "def foo" in r.diff


class TestSchemaRegistry:
    def test_all_schemas_registered(self):
        from dev_guardian.harness.schema import get_schema
        expected = [
            "GatekeeperReport", "RedTeamReport", "DebateResolution",
            "RemediationResult", "HotfixBlueprint", "MigrationBlueprint",
            "PatternCypher", "ADRDraft", "WikiSection",
            "StructureExplanation", "IncidentTriage",
        ]
        for name in expected:
            cls = get_schema(name)
            assert cls.__name__ == name

    def test_unknown_schema_raises_key_error(self):
        from dev_guardian.harness.schema import get_schema
        with pytest.raises(KeyError):
            get_schema("NonExistentSchema")
