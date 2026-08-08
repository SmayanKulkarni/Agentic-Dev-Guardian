"""
Code Review Skills — Gatekeeper, Red Team, Debate, Remediation.
"""
from dev_guardian.harness.schema import (
    DebateResolution,
    GatekeeperReport,
    RedTeamReport,
    RemediationResult,
    parse_debate,
    parse_gatekeeper,
    parse_redteam,
    parse_remediation,
)
from dev_guardian.harness.skill_router import _SKILL_REGISTRY, _SkillRegistration


def register_code_review_skills() -> None:
    """Register gatekeeper, red_team, debate, remediation skills."""
    _SKILL_REGISTRY["architectural_gatekeeper"] = _SkillRegistration(
        name="architectural_gatekeeper",
        prompt_id="gatekeeper",
        version=1,
        schema_cls=GatekeeperReport,
        parser=parse_gatekeeper,
        temperature=0.1,
        max_tokens=1024,
    )
    _SKILL_REGISTRY["adversarial_redteam"] = _SkillRegistration(
        name="adversarial_redteam",
        prompt_id="red_team",
        version=1,
        schema_cls=RedTeamReport,
        parser=parse_redteam,
        temperature=0.3,
        max_tokens=2048,
    )
    _SKILL_REGISTRY["debate_mediator"] = _SkillRegistration(
        name="debate_mediator",
        prompt_id="debate",
        version=1,
        schema_cls=DebateResolution,
        parser=parse_debate,
        temperature=0.0,
        max_tokens=256,
    )
    _SKILL_REGISTRY["remediation_specialist"] = _SkillRegistration(
        name="remediation_specialist",
        prompt_id="remediation",
        version=1,
        schema_cls=RemediationResult,
        parser=parse_remediation,
        temperature=0.2,
        max_tokens=4096,
    )
