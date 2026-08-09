"""
Incident Response Skills — HotfixScribe, SandboxReproducer.
"""
from dev_guardian.harness.schema import (
    HotfixBlueprint,
    IncidentTriage,
)
from dev_guardian.harness.skill_router import _SKILL_REGISTRY, _SkillRegistration


def _parse_hotfix(raw: str) -> HotfixBlueprint:
    import re
    def _section(header: str) -> str:
        upper = raw.upper()
        hdr = header.upper() + ":"
        if hdr not in upper:
            return ""
        idx = upper.index(hdr)
        after = raw[idx + len(hdr):].strip()
        nxt = re.search(r'\n[A-Z][A-Z _]+:\s', after)
        return after[:nxt.start()].strip() if nxt else after.strip()

    return HotfixBlueprint(
        root_cause=_section("ROOT_CAUSE") or raw[:200],
        immediate_mitigation=_section("IMMEDIATE_MITIGATION"),
        full_fix=_section("FULL_FIX"),
        verification=_section("VERIFICATION"),
    )


def _parse_incident_triage(raw: str) -> IncidentTriage:
    import re
    def _field(key: str) -> str:
        m = re.search(rf"^{key}:\s*(.+)$", raw, re.IGNORECASE | re.MULTILINE)
        return m.group(1).strip() if m else ""

    verdict_raw = _field("REPRODUCTION_VERDICT").lower()
    verdict = "confirmed" if "confirmed" in verdict_raw else "inconclusive"
    return IncidentTriage(
        failing_function=_field("FAILING_FUNCTION") or "unknown",
        exception_type=_field("EXCEPTION_TYPE") or "unknown",
        reproduction_verdict=verdict,
        summary=_field("SUMMARY") or raw[:200],
    )


def register_incident_response_skills() -> None:
    """Register hotfix_scribe and sandbox_reproducer skills."""
    _SKILL_REGISTRY["hotfix_scribe"] = _SkillRegistration(
        name="hotfix_scribe",
        prompt_id="hotfix_scribe",
        version=1,
        schema_cls=HotfixBlueprint,
        parser=_parse_hotfix,
        temperature=0.1,
        max_tokens=2048,
    )
    _SKILL_REGISTRY["sandbox_reproducer"] = _SkillRegistration(
        name="sandbox_reproducer",
        prompt_id="sandbox_reproducer",
        version=1,
        schema_cls=IncidentTriage,
        parser=_parse_incident_triage,
        temperature=0.1,
        max_tokens=512,
    )
