"""
Skills Registration — Phase 1 Harness Engineering.

Import this module to register all Guardian skills with the SkillRouter.
Called once at application startup (from cli.py / mcp_server.py).

Each skill maps to:
  - A prompt YAML in backend/prompts/<id>.v<version>.yaml
  - A Pydantic schema in harness.schema
  - A parser function in harness.schema
"""
from dev_guardian.skills.code_review import register_code_review_skills
from dev_guardian.skills.documentation import register_documentation_skills
from dev_guardian.skills.incident_response import register_incident_response_skills
from dev_guardian.skills.refactoring import register_refactoring_skills


def register_all_skills() -> None:
    """Register every skill with the SkillRouter. Call once at startup."""
    register_code_review_skills()
    register_incident_response_skills()
    register_refactoring_skills()
    register_documentation_skills()
