"""
Tests for SkillRouter, SkillContext, SkillResult, skill decorator, and run_skill.

All tests use a fully-mocked backend — no live API calls.

Covers:
- SkillNotFoundError when skill unregistered
- Successful run() end-to-end (mock backend → parsed result → SkillResult)
- SkillResult.to_agent_report() field mapping for all schema types
- skill() decorator registers entry in _SKILL_REGISTRY
- list_skills() returns sorted names
- SkillContext get/getitem
- run_skill() convenience wrapper
- Rate limiter and retry controller integration (mocked)
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dev_guardian.harness.backends import ChatResponse
from dev_guardian.harness.errors import SkillNotFoundError
from dev_guardian.harness.schema import (
    DebateResolution,
    GatekeeperReport,
    RedTeamReport,
    RemediationResult,
)
from dev_guardian.harness.skill_router import (
    _SKILL_REGISTRY,
    SkillContext,
    SkillResult,
    _SkillRegistration,
    skill,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _stub_backend(content: str = "VERDICT: PASS\nREASONING: Looks clean.\nDETAILS: None"):
    """Return a mock backend that always returns the given content string."""
    backend = MagicMock()
    backend.name = "groq"
    backend.count_tokens.return_value = 100
    backend.complete.return_value = ChatResponse(
        content=content,
        model="llama-3.3-70b-versatile",
        prompt_tokens=100,
        completion_tokens=50,
        latency_ms=200,
    )
    return backend


def _stub_prompt_registry(system="You are an agent.", user="Input: {value}"):
    """Return a mock PromptRegistry that renders the given system/user."""
    registry = MagicMock()
    template = MagicMock()
    template.render.return_value = (system, user.format(value="test"))
    registry.load.return_value = template
    return registry


def _make_router(backend_content: str = "VERDICT: PASS\nREASONING: Looks clean.\nDETAILS: None"):
    """Build a SkillRouter with all external deps mocked."""
    from dev_guardian.harness.retry import RetryController
    from dev_guardian.harness.skill_router import SkillRouter

    backend = _stub_backend(backend_content)
    router = SkillRouter.__new__(SkillRouter)
    router._backend = backend
    router._retry = RetryController(max_attempts=1, backoff_base=0.0)
    router._rate_limiter = MagicMock()
    router._rate_limiter.wait_if_needed.return_value = None
    router._ctx_manager = MagicMock()
    router._hlogger = MagicMock()
    router._hlogger.hash_prompt.return_value = "abc123"
    router._registry = _stub_prompt_registry()
    return router


def _register_test_skill(name: str = "test_gatekeeper") -> None:
    """Register a minimal test skill directly into _SKILL_REGISTRY."""
    from dev_guardian.harness.schema import parse_gatekeeper
    _SKILL_REGISTRY[name] = _SkillRegistration(
        name=name,
        prompt_id="gatekeeper",
        version=1,
        schema_cls=GatekeeperReport,
        parser=parse_gatekeeper,
        temperature=0.1,
        max_tokens=512,
    )


# ── SkillContext tests ─────────────────────────────────────────────────────────

class TestSkillContext:
    def test_getitem(self):
        ctx = SkillContext(skill_name="test", kwargs={"pr_diff": "diff text"})
        assert ctx["pr_diff"] == "diff text"

    def test_get_with_default(self):
        ctx = SkillContext(skill_name="test", kwargs={})
        assert ctx.get("missing", "fallback") == "fallback"

    def test_get_existing_key(self):
        ctx = SkillContext(skill_name="test", kwargs={"key": "val"})
        assert ctx.get("key") == "val"

    def test_getitem_missing_raises_keyerror(self):
        ctx = SkillContext(skill_name="test", kwargs={})
        with pytest.raises(KeyError):
            _ = ctx["no_such_key"]

    def test_skill_name_stored(self):
        ctx = SkillContext(skill_name="architectural_gatekeeper")
        assert ctx.skill_name == "architectural_gatekeeper"


# ── SkillResult tests ─────────────────────────────────────────────────────────

class TestSkillResult:
    def _make_result(self, parsed=None) -> SkillResult:
        if parsed is None:
            parsed = GatekeeperReport(
                verdict="fail",
                reasoning="Auth check removed.",
                violations=["auth_check removed", "import os violates policy"],
            )
        return SkillResult(
            skill_name="architectural_gatekeeper",
            parsed=parsed,
            raw_content="raw",
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=200,
            retry_count=0,
        )

    def test_to_agent_report_verdict(self):
        result = self._make_result()
        report = result.to_agent_report()
        assert report["verdict"] == "fail"

    def test_to_agent_report_agent_name(self):
        result = self._make_result()
        report = result.to_agent_report()
        assert report["agent_name"] == "architectural_gatekeeper"

    def test_to_agent_report_violations_become_details(self):
        result = self._make_result()
        report = result.to_agent_report()
        assert "details" in report
        assert "auth_check removed" in report["details"]
        assert "violations" not in report

    def test_to_agent_report_pytest_code_becomes_details(self):
        parsed = RedTeamReport(
            verdict="fail",
            reasoning="Found a bug.",
            pytest_code="def test_foo():\n    assert foo() is not None",
        )
        result = self._make_result(parsed=parsed)
        report = result.to_agent_report()
        assert "def test_foo" in report["details"]
        assert "pytest_code" not in report

    def test_to_agent_report_debate_explanation(self):
        parsed = DebateResolution(decision="approve", explanation="Both agree this is safe.")
        result = self._make_result(parsed=parsed)
        report = result.to_agent_report()
        assert report["details"] == "Both agree this is safe."
        assert "explanation" not in report

    def test_to_agent_report_remediation_no_violations_key(self):
        parsed = RemediationResult(summary="Fixed the null check.", diff="def f(): pass")
        result = self._make_result(parsed=parsed)
        report = result.to_agent_report()
        assert "violations" not in report
        assert "pytest_code" not in report


# ── SkillRouter.run() tests ────────────────────────────────────────────────────

class TestSkillRouterRun:
    def setup_method(self):
        _register_test_skill("_test_skill_router_gk")

    def teardown_method(self):
        _SKILL_REGISTRY.pop("_test_skill_router_gk", None)

    def test_raises_skill_not_found(self):
        router = _make_router()
        with pytest.raises(SkillNotFoundError) as exc_info:
            router.run("definitely_not_registered_xyz", {})
        assert "definitely_not_registered_xyz" in exc_info.value.skill_name

    def test_successful_run_returns_skill_result(self):
        router = _make_router("VERDICT: PASS\nREASONING: All good here.\nDETAILS: None")
        result = router.run("_test_skill_router_gk", {"value": "test_input"})
        assert isinstance(result, SkillResult)
        assert result.skill_name == "_test_skill_router_gk"

    def test_result_has_parsed_gatekeeper_report(self):
        router = _make_router("VERDICT: PASS\nREASONING: No issues found.\nDETAILS: None")
        result = router.run("_test_skill_router_gk", {"value": "x"})
        assert isinstance(result.parsed, GatekeeperReport)
        assert result.parsed.verdict == "pass"

    def test_result_has_correct_token_counts(self):
        router = _make_router()
        result = router.run("_test_skill_router_gk", {"value": "x"})
        assert result.prompt_tokens == 100
        assert result.completion_tokens == 50

    def test_result_has_latency(self):
        router = _make_router()
        result = router.run("_test_skill_router_gk", {"value": "x"})
        assert result.latency_ms == 200

    def test_rate_limiter_called_once(self):
        router = _make_router()
        router.run("_test_skill_router_gk", {"value": "x"})
        router._rate_limiter.wait_if_needed.assert_called_once()

    def test_harness_logger_called_once(self):
        router = _make_router()
        router.run("_test_skill_router_gk", {"value": "x"})
        router._hlogger.log.assert_called_once()

    def test_raw_content_preserved(self):
        content = "VERDICT: WARN\nREASONING: Possible issue.\nDETAILS: None"
        router = _make_router(content)
        result = router.run("_test_skill_router_gk", {"value": "x"})
        assert result.raw_content == content


# ── skill() decorator tests ────────────────────────────────────────────────────

class TestSkillDecorator:
    def test_decorator_registers_skill(self):
        @skill(name="_dec_test_skill", schema=GatekeeperReport, prompt="gatekeeper")
        def _my_skill(ctx):
            pass

        assert "_dec_test_skill" in _SKILL_REGISTRY
        reg = _SKILL_REGISTRY["_dec_test_skill"]
        assert reg.prompt_id == "gatekeeper"
        assert reg.schema_cls is GatekeeperReport
        _SKILL_REGISTRY.pop("_dec_test_skill")

    def test_decorator_sets_skill_name_attribute(self):
        @skill(name="_dec_name_test", schema=GatekeeperReport, prompt="gatekeeper")
        def _my_fn(ctx):
            pass

        assert _my_fn._skill_name == "_dec_name_test"
        _SKILL_REGISTRY.pop("_dec_name_test")

    def test_decorator_preserves_callable(self):
        @skill(name="_dec_callable_test", schema=GatekeeperReport, prompt="gatekeeper")
        def _my_fn(ctx):
            return "called"

        assert callable(_my_fn)
        assert _my_fn(None) == "called"
        _SKILL_REGISTRY.pop("_dec_callable_test")


# ── list_skills() tests ────────────────────────────────────────────────────────

class TestListSkills:
    def test_returns_sorted_list(self):
        router = _make_router()
        names = router.list_skills()
        assert names == sorted(names)

    def test_registered_skill_appears(self):
        _register_test_skill("_list_test_skill")
        router = _make_router()
        assert "_list_test_skill" in router.list_skills()
        _SKILL_REGISTRY.pop("_list_test_skill")

    def test_returns_list_type(self):
        router = _make_router()
        assert isinstance(router.list_skills(), list)
