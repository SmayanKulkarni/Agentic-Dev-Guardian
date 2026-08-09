"""Per-client MCP config shapes and the preload escape hatch.

The three clients Guardian targets disagree on where the server block lives:
VS Code keys it under `servers`, Codex reads TOML, everyone else copied
Claude Desktop's `mcpServers`. A wrong shape fails silently in the IDE, so
each one is pinned here.
"""
from __future__ import annotations

import json

import pytest

from dev_guardian.cli import MCP_CLIENTS, _mcp_config_json
from dev_guardian.mcp_server import resolve_preload


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("GUARDIAN_PROVIDER", "GUARDIAN_MODEL", "GUARDIAN_PRELOAD_CLUSTERS"):
        monkeypatch.delenv(var, raising=False)


# ── Config shapes ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("client", ["claude", "cursor", "windsurf", "antigravity"])
def test_mcpservers_clients_share_the_claude_desktop_shape(client):
    block = json.loads(_mcp_config_json(client))

    assert block["mcpServers"]["guardian"]["command"] == "uvx"
    assert "serve" in block["mcpServers"]["guardian"]["args"]


def test_vscode_uses_servers_key_with_an_explicit_transport():
    block = json.loads(_mcp_config_json("vscode"))

    assert "mcpServers" not in block
    assert block["servers"]["guardian"]["type"] == "stdio"


def test_codex_emits_toml_not_json():
    text = _mcp_config_json("codex")

    assert text.startswith("[mcp_servers.guardian]")
    assert '[mcp_servers.guardian.env]' in text
    assert 'command = "uvx"' in text
    with pytest.raises(json.JSONDecodeError):
        json.loads(text)


def test_every_advertised_client_renders():
    for client in MCP_CLIENTS:
        assert _mcp_config_json(client).strip()


def test_unknown_client_raises():
    with pytest.raises(KeyError):
        _mcp_config_json("emacs")


def test_api_key_is_a_placeholder_never_the_resolved_secret(monkeypatch):
    monkeypatch.setenv("GUARDIAN_PROVIDER", "groq")
    monkeypatch.setenv("GUARDIAN_GROQ_API_KEY", "gsk-super-secret")

    for client in MCP_CLIENTS:
        assert "gsk-super-secret" not in _mcp_config_json(client)


def test_local_providers_get_no_api_key_line(monkeypatch):
    monkeypatch.setenv("GUARDIAN_PROVIDER", "ollama")

    block = json.loads(_mcp_config_json("claude"))
    env = block["mcpServers"]["guardian"]["env"]

    assert env["GUARDIAN_PROVIDER"] == "ollama"
    assert not [k for k in env if k.endswith("API_KEY")]


def test_preload_setting_propagates_into_the_emitted_env(monkeypatch):
    monkeypatch.setenv("GUARDIAN_PRELOAD_CLUSTERS", "all")

    block = json.loads(_mcp_config_json("claude"))

    assert block["mcpServers"]["guardian"]["env"]["GUARDIAN_PRELOAD_CLUSTERS"] == "all"


# ── Preload resolution ───────────────────────────────────────────────────────


def test_preload_unset_equips_nothing():
    assert resolve_preload(None) == []
    assert resolve_preload("  ") == []


def test_preload_all_equips_every_registered_cluster():
    from dev_guardian.capability_clusters.core import CLUSTER_REGISTRY

    assert sorted(resolve_preload("ALL")) == sorted(CLUSTER_REGISTRY)


def test_preload_accepts_a_comma_list_and_drops_stale_names():
    assert resolve_preload("pr_governance, nope") == ["pr_governance"]
