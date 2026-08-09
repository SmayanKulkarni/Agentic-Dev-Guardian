"""
PromptRegistry — version-controlled prompt templates shipped inside the
package at dev_guardian/prompts/*.yaml.

File format (YAML):
    id: gatekeeper
    version: 1
    system: |
        You are the Gatekeeper Agent...
    user_template: |
        ## PR Diff
        {pr_diff}
        ## GraphRAG Context
        {context}
    schema: GatekeeperReport

Prompts live inside the package so the same path resolves for a source
checkout and for an installed wheel.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from dev_guardian.harness.errors import PromptNotFoundError

# Default location: the packaged dev_guardian/prompts/ directory. Resolves
# identically from a source checkout and from site-packages.
_DEFAULT_ROOT = Path(__file__).parents[1] / "prompts"


class PromptTemplate(BaseModel):
    """A single versioned prompt template loaded from YAML."""

    id: str
    version: int
    system: str
    user_template: str
    schema: str

    def render(self, **kwargs: Any) -> tuple[str, str]:
        """
        Render the template with the given variables.

        Returns:
            Tuple of (system_prompt, rendered_user_message).

        Raises:
            KeyError: If a required template variable is missing.
        """
        try:
            user = self.user_template.format(**kwargs)
        except KeyError as exc:
            raise KeyError(
                f"Prompt '{self.id}' requires variable {exc} — "
                f"available: {list(kwargs)}"
            ) from exc
        return self.system, user


class PromptRegistry:
    """
    Loads and caches PromptTemplates from YAML files on disk.

    File naming convention:
        dev_guardian/prompts/<id>.v<version>.yaml
        or
        dev_guardian/prompts/<id>.yaml   (treated as version=1)
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or _DEFAULT_ROOT
        self._cache: dict[str, dict[int, PromptTemplate]] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        if not self._root.exists():
            self._loaded = True
            return
        for fpath in sorted(self._root.glob("*.yaml")):
            self._load_file(fpath)
        self._loaded = True

    def _load_file(self, fpath: Path) -> None:
        try:
            data = yaml.safe_load(fpath.read_text(encoding="utf-8"))
            tpl = PromptTemplate(**data)
            self._cache.setdefault(tpl.id, {})[tpl.version] = tpl
        except Exception as exc:
            import warnings
            warnings.warn(f"Failed to load prompt file {fpath}: {exc}", stacklevel=2)

    def load(self, prompt_id: str, version: int | str = "latest") -> PromptTemplate:
        """
        Load a PromptTemplate by id and version.

        Args:
            prompt_id: The id field from the YAML file.
            version: Integer version, or "latest" for the highest available.

        Raises:
            PromptNotFoundError: If no matching template is found.
        """
        self._ensure_loaded()
        versions = self._cache.get(prompt_id)
        if not versions:
            raise PromptNotFoundError(prompt_id)

        if version == "latest":
            return versions[max(versions)]
        if isinstance(version, int) and version in versions:
            return versions[version]

        raise PromptNotFoundError(f"{prompt_id}.v{version}")

    def list(self) -> list[str]:
        """Return sorted list of registered prompt IDs."""
        self._ensure_loaded()
        return sorted(self._cache.keys())

    def reload(self) -> None:
        """Force reload of all prompt files (useful in dev)."""
        self._cache.clear()
        self._loaded = False
        self._ensure_loaded()


# Module-level singleton
_registry: PromptRegistry | None = None


def get_prompt_registry() -> PromptRegistry:
    global _registry
    if _registry is None:
        _registry = PromptRegistry()
    return _registry
