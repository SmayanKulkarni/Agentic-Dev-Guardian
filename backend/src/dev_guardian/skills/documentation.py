"""
Documentation Skills — StructureExplainer, ADRGenerator, WikiBuilder.
"""
from dev_guardian.harness.schema import ADRDraft, StructureExplanation, WikiSection
from dev_guardian.harness.skill_router import _SKILL_REGISTRY, _SkillRegistration


def _parse_structure_explanation(raw: str) -> StructureExplanation:
    return StructureExplanation(explanation=raw.strip() or "No explanation generated.")


def _parse_adr_draft(raw: str) -> ADRDraft:
    import re
    def _section(header: str) -> str:
        upper = raw.upper()
        hdr = header.upper() + "\n"
        if hdr not in upper:
            return ""
        idx = upper.index(hdr)
        after = raw[idx + len(hdr):].strip()
        nxt = re.search(r'\n## ', after)
        return after[:nxt.start()].strip() if nxt else after.strip()

    return ADRDraft(
        context=_section("## CONTEXT") or raw[:200],
        decision=_section("## DECISION") or raw[:200],
        consequences=_section("## CONSEQUENCES"),
    )


def _parse_wiki_section(raw: str) -> WikiSection:
    return WikiSection(content=raw.strip() or "No wiki content generated.")


def register_documentation_skills() -> None:
    """Register structure_explainer, adr_generator, wiki_builder skills."""
    _SKILL_REGISTRY["structure_explainer"] = _SkillRegistration(
        name="structure_explainer",
        prompt_id="structure_explainer",
        version=1,
        schema_cls=StructureExplanation,
        parser=_parse_structure_explanation,
        temperature=0.3,
        max_tokens=400,
    )
    _SKILL_REGISTRY["adr_generator"] = _SkillRegistration(
        name="adr_generator",
        prompt_id="adr_generator",
        version=1,
        schema_cls=ADRDraft,
        parser=_parse_adr_draft,
        temperature=0.2,
        max_tokens=500,
    )
    _SKILL_REGISTRY["wiki_builder"] = _SkillRegistration(
        name="wiki_builder",
        prompt_id="wiki_builder",
        version=1,
        schema_cls=WikiSection,
        parser=_parse_wiki_section,
        temperature=0.3,
        max_tokens=2048,
    )
