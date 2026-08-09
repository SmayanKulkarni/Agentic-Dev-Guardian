"""
Golden-output tests for surviving free-text parsers.

The gatekeeper/red_team/remediation _parse_* helpers were removed when
the legacy GUARDIAN_USE_HARNESS=0 direct-Groq path was migrated onto
SkillRouter (see .scratch/ship-guardian/issues/04-provider-selection-contract.md);
their coverage now lives in dev_guardian.harness.schema's parse_* tests.
This file keeps the parsers that are still part of the codebase.
"""
from __future__ import annotations

import pytest

# ── Incident triager _parse_stack_trace ──────────────────────────────────────

pytestmark_gqlalchemy = pytest.mark.skipif(
    __import__("importlib").util.find_spec("gqlalchemy") is None,
    reason="gqlalchemy not installed",
)


@pytestmark_gqlalchemy
class TestStackTraceParse:
    def _parse(self, trace: str):
        from dev_guardian.agents.incident_triager import _parse_stack_trace
        return _parse_stack_trace(trace)

    PYTHON_TRACE = (
        'Traceback (most recent call last):\n'
        '  File "/home/user/app/main.py", line 10, in run\n'
        '    result = process(data)\n'
        '  File "/home/user/app/processor.py", line 42, in process\n'
        '    return transform(data["key"])\n'
        'KeyError: \'key\'\n'
    )

    def test_failing_function_extracted(self):
        r = self._parse(self.PYTHON_TRACE)
        assert r["failing_function"] == "process"

    def test_exception_type_extracted(self):
        r = self._parse(self.PYTHON_TRACE)
        assert r["exception_type"] == "KeyError"

    def test_frames_populated(self):
        r = self._parse(self.PYTHON_TRACE)
        assert len(r["frames"]) >= 2

    def test_empty_trace_returns_empty(self):
        r = self._parse("")
        assert r["failing_function"] == ""
        assert r["frames"] == []
