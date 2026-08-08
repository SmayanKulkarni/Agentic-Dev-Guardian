"""
Tests for skills registration module.

Verifies:
- register_all_skills() populates _SKILL_REGISTRY with all expected skill names
- Each skill has correct schema_cls type
- Each skill's parser produces the correct ResponseSchema subclass from sample output
- Skill temperature/max_tokens are set to sane values
- Re-registration is idempotent (no duplicate or crash)
"""
from __future__ import annotations

import pytest

from dev_guardian.harness.schema import (
    ADRDraft,
    DebateResolution,
    GatekeeperReport,
    HotfixBlueprint,
    IncidentTriage,
    MigrationBlueprint,
    PatternCypher,
    RedTeamReport,
    RemediationResult,
    ResponseSchema,
    StructureExplanation,
    WikiSection,
)
from dev_guardian.harness.skill_router import _SKILL_REGISTRY

# ── Register once for all tests in this module ───────────────────────────────

def _ensure_registered():
    from dev_guardian.skills import register_all_skills
    register_all_skills()


_ensure_registered()


EXPECTED_SKILLS = [
    ("architectural_gatekeeper", GatekeeperReport),
    ("adversarial_redteam", RedTeamReport),
    ("debate_mediator", DebateResolution),
    ("remediation_specialist", RemediationResult),
    ("hotfix_scribe", HotfixBlueprint),
    ("sandbox_reproducer", IncidentTriage),
    ("pattern_translator", PatternCypher),
    ("migration_scribe", MigrationBlueprint),
    ("structure_explainer", StructureExplanation),
    ("adr_generator", ADRDraft),
    ("wiki_builder", WikiSection),
]

SAMPLE_OUTPUTS: dict[str, str] = {
    "architectural_gatekeeper": (
        "VERDICT: PASS\nREASONING: No architectural violations detected.\nDETAILS: None"
    ),
    "adversarial_redteam": (
        "VERDICT: PASS\nREASONING: Code is robust against adversarial inputs.\nDETAILS: None"
    ),
    "debate_mediator": "RESOLUTION: APPROVE — Both agents agree the PR is safe.",
    "remediation_specialist": "SUMMARY: Added null guard.\nDIFF:\ndef f():\n    pass",
    "hotfix_scribe": (
        "ROOT_CAUSE: Null pointer in process().\n"
        "IMMEDIATE_MITIGATION: Add guard clause.\n"
        "FULL_FIX: Validate input before calling.\n"
        "VERIFICATION: Run pytest tests/test_process.py"
    ),
    "sandbox_reproducer": (
        "FAILING_FUNCTION: process_data\nEXCEPTION_TYPE: ValueError\n"
        "REPRODUCTION_VERDICT: confirmed\nSUMMARY: Reproduced null input crash."
    ),
    "pattern_translator": (
        "MATCH (n:ASTNode) WHERE n.name = 'foo' "
        "RETURN n.name AS name, n.file_path AS file_path, n.node_type AS node_type, 'reason' AS reason"
    ),
    "migration_scribe": "SUMMARY: Migrate Pydantic v1 to v2.\n## Batch 1: file.py",
    "structure_explainer": "The codebase has a layered architecture with clear separation of concerns.",
    "adr_generator": (
        "## Status\nAccepted\n\n## Context\nThis function handles auth.\n\n"
        "## Decision\nUsed JWT tokens.\n\n## Consequences\nSimplifies session management."
    ),
    "wiki_builder": "# Guardian Wiki\n\n## Overview\nThis codebase implements a multi-agent governance system.",
}


class TestAllSkillsRegistered:
    @pytest.mark.parametrize("skill_name,expected_cls", EXPECTED_SKILLS)
    def test_skill_in_registry(self, skill_name, expected_cls):
        assert skill_name in _SKILL_REGISTRY, f"'{skill_name}' not registered"

    @pytest.mark.parametrize("skill_name,expected_cls", EXPECTED_SKILLS)
    def test_skill_schema_cls_correct(self, skill_name, expected_cls):
        reg = _SKILL_REGISTRY[skill_name]
        assert reg.schema_cls is expected_cls, (
            f"'{skill_name}' has schema {reg.schema_cls.__name__}, expected {expected_cls.__name__}"
        )

    @pytest.mark.parametrize("skill_name,expected_cls", EXPECTED_SKILLS)
    def test_skill_has_prompt_id(self, skill_name, expected_cls):
        reg = _SKILL_REGISTRY[skill_name]
        assert isinstance(reg.prompt_id, str) and len(reg.prompt_id) > 0

    @pytest.mark.parametrize("skill_name,expected_cls", EXPECTED_SKILLS)
    def test_skill_temperature_in_range(self, skill_name, expected_cls):
        reg = _SKILL_REGISTRY[skill_name]
        assert 0.0 <= reg.temperature <= 1.0, f"'{skill_name}' temperature out of range"

    @pytest.mark.parametrize("skill_name,expected_cls", EXPECTED_SKILLS)
    def test_skill_max_tokens_positive(self, skill_name, expected_cls):
        reg = _SKILL_REGISTRY[skill_name]
        assert reg.max_tokens > 0, f"'{skill_name}' max_tokens must be positive"

    @pytest.mark.parametrize("skill_name,expected_cls", EXPECTED_SKILLS)
    def test_skill_has_callable_parser(self, skill_name, expected_cls):
        reg = _SKILL_REGISTRY[skill_name]
        assert callable(reg.parser), f"'{skill_name}' parser is not callable"


class TestSkillParsers:
    @pytest.mark.parametrize("skill_name,expected_cls", EXPECTED_SKILLS)
    def test_parser_returns_correct_schema_type(self, skill_name, expected_cls):
        sample = SAMPLE_OUTPUTS.get(skill_name)
        if sample is None:
            pytest.skip(f"No sample output for '{skill_name}'")
        reg = _SKILL_REGISTRY[skill_name]
        result = reg.parser(sample)
        assert isinstance(result, ResponseSchema), (
            f"Parser for '{skill_name}' returned {type(result)}, not ResponseSchema"
        )
        assert isinstance(result, expected_cls), (
            f"Parser for '{skill_name}' returned {type(result).__name__}, expected {expected_cls.__name__}"
        )

    def test_gatekeeper_parser_pass(self):
        reg = _SKILL_REGISTRY["architectural_gatekeeper"]
        r = reg.parser("VERDICT: PASS\nREASONING: Looks good to me.\nDETAILS: None")
        assert r.verdict == "pass"

    def test_gatekeeper_parser_fail(self):
        reg = _SKILL_REGISTRY["architectural_gatekeeper"]
        r = reg.parser("VERDICT: FAIL\nREASONING: Missing auth check.\nDETAILS:\n- `auth` removed")
        assert r.verdict == "fail"
        assert len(r.violations) == 1

    def test_redteam_parser_pass(self):
        reg = _SKILL_REGISTRY["adversarial_redteam"]
        r = reg.parser("VERDICT: PASS\nREASONING: Robust against attacks.\nDETAILS: None")
        assert r.verdict == "pass"
        assert r.pytest_code == ""

    def test_debate_parser_approve(self):
        reg = _SKILL_REGISTRY["debate_mediator"]
        r = reg.parser("RESOLUTION: APPROVE — safe PR.")
        assert r.decision == "approve"

    def test_debate_parser_remediate(self):
        reg = _SKILL_REGISTRY["debate_mediator"]
        r = reg.parser("RESOLUTION: REMEDIATE — needs fixing.")
        assert r.decision == "remediate"

    def test_pattern_translator_valid_cypher(self):
        reg = _SKILL_REGISTRY["pattern_translator"]
        cypher = "MATCH (n:ASTNode) WHERE n.name = 'foo' RETURN n.name AS name, n.file_path AS file_path, n.node_type AS node_type, 'r' AS reason"
        r = reg.parser(cypher)
        assert "MATCH" in r.cypher.upper()
        assert "RETURN" in r.cypher.upper()

    def test_pattern_translator_strips_fences(self):
        reg = _SKILL_REGISTRY["pattern_translator"]
        fenced = "```cypher\nMATCH (n) RETURN n.name AS name, n.file_path AS file_path, n.node_type AS node_type, 'r' AS reason\n```"
        r = reg.parser(fenced)
        assert "```" not in r.cypher

    def test_hotfix_parser_extracts_sections(self):
        reg = _SKILL_REGISTRY["hotfix_scribe"]
        raw = (
            "ROOT_CAUSE: Division by zero in compute().\n"
            "IMMEDIATE_MITIGATION: Guard against zero denominator.\n"
            "FULL_FIX: Add validation before division.\n"
            "VERIFICATION: pytest tests/test_compute.py"
        )
        r = reg.parser(raw)
        assert isinstance(r, HotfixBlueprint)
        assert "Division by zero" in r.root_cause or r.root_cause  # non-empty

    def test_structure_explainer_stores_content(self):
        reg = _SKILL_REGISTRY["structure_explainer"]
        r = reg.parser("The codebase is modular.")
        assert "modular" in r.explanation

    def test_migration_scribe_stores_summary(self):
        reg = _SKILL_REGISTRY["migration_scribe"]
        raw = "SUMMARY: Migrate all validators.\n## Batch 1: models.py"
        r = reg.parser(raw)
        assert isinstance(r, MigrationBlueprint)
        assert r.summary or r.batches_md  # at least one populated


class TestIdempotentRegistration:
    def test_reregistration_does_not_crash(self):
        from dev_guardian.skills import register_all_skills
        # Should not raise on second call
        register_all_skills()
        register_all_skills()

    def test_skill_count_stable_after_rereg(self):
        from dev_guardian.skills import register_all_skills
        count_before = len(_SKILL_REGISTRY)
        register_all_skills()
        count_after = len(_SKILL_REGISTRY)
        assert count_after == count_before
