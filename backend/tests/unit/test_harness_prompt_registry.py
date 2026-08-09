"""
Phase 1 — Unit tests for PromptRegistry YAML loading and rendering.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dev_guardian.harness.errors import PromptNotFoundError
from dev_guardian.harness.prompt_registry import PromptRegistry

_SAMPLE_YAML = """\
id: test_prompt
version: 1
schema: GatekeeperReport
system: |
  You are a test agent.
user_template: |
  Input: {value}
"""


class TestPromptRegistry:
    def _registry_with_prompt(self, content: str = _SAMPLE_YAML) -> PromptRegistry:
        tmpdir = tempfile.mkdtemp()
        (Path(tmpdir) / "test_prompt.yaml").write_text(content)
        return PromptRegistry(root=Path(tmpdir))

    def test_load_existing_prompt(self):
        reg = self._registry_with_prompt()
        tpl = reg.load("test_prompt")
        assert tpl.id == "test_prompt"
        assert tpl.version == 1
        assert tpl.schema == "GatekeeperReport"

    def test_render_with_variables(self):
        reg = self._registry_with_prompt()
        tpl = reg.load("test_prompt")
        system, user = tpl.render(value="hello world")
        assert "You are a test agent" in system
        assert "hello world" in user

    def test_render_missing_variable_raises(self):
        reg = self._registry_with_prompt()
        tpl = reg.load("test_prompt")
        with pytest.raises(KeyError):
            tpl.render()  # missing 'value'

    def test_load_nonexistent_raises(self):
        reg = self._registry_with_prompt()
        with pytest.raises(PromptNotFoundError):
            reg.load("nonexistent_prompt")

    def test_list_returns_ids(self):
        reg = self._registry_with_prompt()
        ids = reg.list()
        assert "test_prompt" in ids

    def test_reload_picks_up_new_file(self):
        tmpdir = tempfile.mkdtemp()
        reg = PromptRegistry(root=Path(tmpdir))
        assert reg.list() == []
        (Path(tmpdir) / "new_prompt.yaml").write_text(
            "id: new_prompt\nversion: 1\nschema: RedTeamReport\n"
            "system: sys\nuser_template: user {x}\n"
        )
        reg.reload()
        assert "new_prompt" in reg.list()

    def test_version_latest_returns_highest(self):
        tmpdir = tempfile.mkdtemp()
        for v in (1, 2, 3):
            (Path(tmpdir) / "versioned.yaml").write_text(
                f"id: versioned\nversion: {v}\nschema: GatekeeperReport\n"
                "system: sys\nuser_template: u\n"
            )
        reg = PromptRegistry(root=Path(tmpdir))
        tpl = reg.load("versioned", version="latest")
        assert tpl.version == 3

    def test_empty_root_returns_empty_list(self):
        reg = PromptRegistry(root=Path("/nonexistent_path_xyz"))
        assert reg.list() == []


class TestPromptRegistryWithRealFiles:
    """Load actual prompt YAMLs from the backend/prompts/ directory."""

    def test_gatekeeper_prompt_loads(self):
        from dev_guardian.harness.prompt_registry import get_prompt_registry
        reg = get_prompt_registry()
        tpl = reg.load("gatekeeper")
        assert tpl.schema == "GatekeeperReport"
        assert "{pr_diff}" in tpl.user_template

    def test_all_real_prompts_render(self):
        from dev_guardian.harness.prompt_registry import get_prompt_registry
        reg = get_prompt_registry()
        prompts_and_vars = {
            "gatekeeper": {"pr_diff": "diff text", "context": "ctx"},
            "red_team": {"pr_diff": "diff text", "context": "ctx"},
            "debate": {
                "gk_verdict": "PASS", "gk_reasoning": "ok",
                "rt_verdict": "FAIL", "rt_reasoning": "bad",
                "context": "ctx",
            },
        }
        for pid, vars_ in prompts_and_vars.items():
            tpl = reg.load(pid)
            system, user = tpl.render(**vars_)
            assert len(system) > 10
            assert len(user) > 5

    def test_default_root_ships_inside_the_package(self):
        """Guards the packaging contract: prompts must resolve relative to the
        installed package, not to a repo layout that vanishes in site-packages."""
        from dev_guardian.harness import prompt_registry as mod

        assert mod._DEFAULT_ROOT.is_dir(), f"{mod._DEFAULT_ROOT} does not exist"
        shipped = {f.stem.split(".v")[0] for f in mod._DEFAULT_ROOT.glob("*.yaml")}
        assert shipped, "no prompt YAML shipped inside the package"
        assert shipped <= set(mod.PromptRegistry().list())
