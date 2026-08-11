"""
The MCP config block is what a user pastes into their IDE. With the backing
stores embedded, it must name the repository Guardian indexes — not host/port
pairs for services that no longer exist.
"""
from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from dev_guardian.cli import app

runner = CliRunner()


def test_config_block_names_the_repo_and_not_the_old_services(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["mcp-config"])

    assert result.exit_code == 0
    env = json.loads(result.stdout)["mcpServers"]["guardian"]["env"]
    assert env["GUARDIAN_REPO"] == str(tmp_path.resolve())
    assert not [k for k in env if "MEMGRAPH" in k or "QDRANT" in k]


def test_vscode_shape_is_kept(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["mcp-config", "--client", "vscode"])

    assert result.exit_code == 0
    assert "servers" in json.loads(result.stdout)


def test_unknown_client_exits_two(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["mcp-config", "--client", "emacs"])

    assert result.exit_code == 2


@pytest.mark.parametrize("removed", ["init", "down"])
def test_docker_commands_are_gone(removed):
    result = runner.invoke(app, [removed, "--help"])

    assert result.exit_code != 0
