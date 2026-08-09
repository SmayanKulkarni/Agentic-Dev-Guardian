"""
Refactoring Skills — PatternTranslator, MigrationScribe.
"""
from dev_guardian.harness.schema import MigrationBlueprint, PatternCypher
from dev_guardian.harness.skill_router import _SKILL_REGISTRY, _SkillRegistration


def _parse_pattern_cypher(raw: str) -> PatternCypher:
    lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            continue
        lines.append(line)
    cypher = "\n".join(lines).strip()
    if not cypher:
        cypher = "MATCH (n:ASTNode) RETURN n.name AS name, n.file_path AS file_path, n.node_type AS node_type, 'fallback' AS reason"
    return PatternCypher(cypher=cypher)


def _parse_migration_blueprint(raw: str) -> MigrationBlueprint:
    import re
    upper = raw.upper()
    summary = ""
    if "SUMMARY:" in upper:
        idx = upper.index("SUMMARY:")
        after = raw[idx + 8:].strip()
        nxt = re.search(r'\n[A-Z][A-Z_]+:', after)
        summary = after[:nxt.start()].strip() if nxt else after[:300].strip()
    return MigrationBlueprint(
        summary=summary or raw[:200],
        batches_md=raw,
    )


def register_refactoring_skills() -> None:
    """Register pattern_translator and migration_scribe skills."""
    _SKILL_REGISTRY["pattern_translator"] = _SkillRegistration(
        name="pattern_translator",
        prompt_id="pattern_translator",
        version=1,
        schema_cls=PatternCypher,
        parser=_parse_pattern_cypher,
        temperature=0.0,
        max_tokens=512,
    )
    _SKILL_REGISTRY["migration_scribe"] = _SkillRegistration(
        name="migration_scribe",
        prompt_id="migration_scribe",
        version=1,
        schema_cls=MigrationBlueprint,
        parser=_parse_migration_blueprint,
        temperature=0.2,
        max_tokens=4096,
    )
