"""
Pydantic response schemas — every LLM response that feeds downstream
logic must validate against a ResponseSchema subclass.

These replace the _parse_report() regex parsers in the original agents.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from dev_guardian.harness.errors import SchemaValidationError

Verdict = Literal["pass", "fail", "warn"]
Decision = Literal["approve", "reject", "remediate"]


class ResponseSchema(BaseModel):
    """Base class. Subclasses are registered by class name in prompt YAML."""


# ── Core agent schemas ────────────────────────────────────────────────────────

class GatekeeperReport(ResponseSchema):
    verdict: Verdict
    reasoning: str = Field(min_length=5)
    violations: list[str] = Field(default_factory=list)


class RedTeamReport(ResponseSchema):
    verdict: Verdict
    reasoning: str = Field(min_length=5)
    pytest_code: str = ""


class DebateResolution(ResponseSchema):
    decision: Decision
    explanation: str = Field(min_length=5)


class RemediationResult(ResponseSchema):
    summary: str = ""
    diff: str = ""


class HotfixBlueprint(ResponseSchema):
    root_cause: str = Field(min_length=5)
    immediate_mitigation: str = ""
    full_fix: str = ""
    verification: str = ""


class MigrationBlueprint(ResponseSchema):
    summary: str = Field(min_length=5)
    batches_md: str = ""


class BlueprintValidation(ResponseSchema):
    verdict: Literal["valid", "valid_with_warnings", "invalid"]
    warnings: list[str] = Field(default_factory=list)


class PatternCypher(ResponseSchema):
    cypher: str = Field(min_length=10)


class ADRDraft(ResponseSchema):
    context: str = Field(min_length=5)
    decision: str = Field(min_length=5)
    consequences: str = ""


class WikiSection(ResponseSchema):
    content: str = Field(min_length=10)


class StructureExplanation(ResponseSchema):
    explanation: str = Field(min_length=10)


class IncidentTriage(ResponseSchema):
    failing_function: str
    exception_type: str
    reproduction_verdict: Literal["confirmed", "inconclusive"] = "inconclusive"
    summary: str = ""


# ── Schema registry ───────────────────────────────────────────────────────────

_REGISTRY: dict[str, type[ResponseSchema]] = {
    cls.__name__: cls
    for cls in [
        GatekeeperReport,
        RedTeamReport,
        DebateResolution,
        RemediationResult,
        HotfixBlueprint,
        MigrationBlueprint,
        BlueprintValidation,
        PatternCypher,
        ADRDraft,
        WikiSection,
        StructureExplanation,
        IncidentTriage,
    ]
}


def get_schema(name: str) -> type[ResponseSchema]:
    """Look up a ResponseSchema subclass by name."""
    if name not in _REGISTRY:
        raise KeyError(f"Schema '{name}' not in registry. Available: {list(_REGISTRY)}")
    return _REGISTRY[name]


# ── Structured text parsers ───────────────────────────────────────────────────

def _extract_verdict(raw: str) -> Verdict:
    for line in raw.splitlines():
        if line.strip().upper().startswith("VERDICT:"):
            v = line.split(":", 1)[1].strip().lower()
            if v in ("pass", "fail", "warn"):
                return v  # type: ignore[return-value]
    return "warn"


def _extract_section(raw: str, header: str) -> str:
    upper = raw.upper()
    hdr = header.upper() + ":"
    if hdr not in upper:
        return ""
    idx = upper.index(hdr)
    after = raw[idx + len(hdr):].strip()
    # Return until the next ALL-CAPS header or end
    next_hdr = re.search(r'\n[A-Z][A-Z _]+:\s', after)
    if next_hdr:
        return after[:next_hdr.start()].strip()
    return after.strip()


def parse_gatekeeper(raw: str) -> GatekeeperReport:
    """Parse a free-text gatekeeper response into GatekeeperReport."""
    verdict = _extract_verdict(raw)
    reasoning = _extract_section(raw, "REASONING") or (raw[:200] if raw else "No reasoning provided.")
    details_raw = _extract_section(raw, "DETAILS")
    violations = [
        line.lstrip("- ").strip()
        for line in details_raw.splitlines()
        if line.strip() and line.strip().lower() not in ("none", "n/a")
    ]
    try:
        return GatekeeperReport(
            verdict=verdict,
            reasoning=reasoning or "No reasoning provided.",
            violations=violations,
        )
    except ValidationError as exc:
        raise SchemaValidationError("GatekeeperReport", raw, str(exc)) from exc


def parse_redteam(raw: str) -> RedTeamReport:
    """Parse a free-text red team response into RedTeamReport."""
    verdict = _extract_verdict(raw)
    reasoning = _extract_section(raw, "REASONING") or (raw[:200] if raw else "No reasoning provided.")
    details = _extract_section(raw, "DETAILS")
    # Filter out 'None' / 'No exploits found' placeholder text
    placeholder = details.strip().lower() in ("none", "no exploits found", "n/a", "")
    pytest_code = details if ("def test_" in details and not placeholder) else ""
    try:
        return RedTeamReport(
            verdict=verdict,
            reasoning=reasoning or "No reasoning provided.",
            pytest_code=pytest_code,
        )
    except ValidationError as exc:
        raise SchemaValidationError("RedTeamReport", raw, str(exc)) from exc


def parse_debate(raw: str) -> DebateResolution:
    """Parse a RESOLUTION: line into DebateResolution."""
    decision: Decision = "remediate"
    explanation = raw.strip()
    upper = raw.upper()
    if "APPROVE" in upper:
        decision = "approve"
    elif "REJECT" in upper:
        decision = "reject"
    elif "REMEDIATE" in upper:
        decision = "remediate"
    try:
        return DebateResolution(decision=decision, explanation=explanation[:500])
    except ValidationError as exc:
        raise SchemaValidationError("DebateResolution", raw, str(exc)) from exc


def parse_remediation(raw: str) -> RemediationResult:
    """Parse a SUMMARY/DIFF response into RemediationResult."""
    if not raw or not raw.strip():
        return RemediationResult(summary="", diff="")
    summary = _extract_section(raw, "SUMMARY") or raw[:200]
    diff_section = _extract_section(raw, "DIFF")
    if "```" in diff_section:
        parts = diff_section.split("```")
        if len(parts) >= 2:
            code = parts[1].lstrip()
            lang_match = re.match(r"^[A-Za-z0-9_+.-]+\n", code)
            if lang_match:
                code = code[lang_match.end():]
            diff_section = code.strip()
    try:
        return RemediationResult(summary=summary, diff=diff_section)
    except ValidationError as exc:
        raise SchemaValidationError("RemediationResult", raw, str(exc)) from exc
