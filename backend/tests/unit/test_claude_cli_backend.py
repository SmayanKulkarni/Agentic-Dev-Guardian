"""Tests for ClaudeCLIBackend — no real `claude` subprocess is invoked."""
from __future__ import annotations

import json
import subprocess

import pytest

from dev_guardian.harness.backends import ChatRequest
from dev_guardian.harness.errors import BackendUnavailableError


def _fake_run(stdout: dict | str, returncode: int = 0):
    payload = stdout if isinstance(stdout, str) else json.dumps(stdout)

    def _run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode, stdout=payload, stderr="")

    return _run


class TestClaudeCLIBackend:
    def test_missing_binary_raises(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: None)
        from dev_guardian.harness.backends.claude_cli_backend import ClaudeCLIBackend

        with pytest.raises(BackendUnavailableError):
            ClaudeCLIBackend()

    def test_complete_parses_result_and_usage(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/claude")
        from dev_guardian.harness.backends.claude_cli_backend import ClaudeCLIBackend

        backend = ClaudeCLIBackend()
        monkeypatch.setattr(
            subprocess,
            "run",
            _fake_run(
                {
                    "is_error": False,
                    "result": "OK",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                    "modelUsage": {"claude-sonnet-5": {"canonicalModel": "claude-sonnet-5"}},
                }
            ),
        )

        resp = backend.complete(ChatRequest(system="sys", user="hi"))

        assert resp.content == "OK"
        assert resp.model == "claude-sonnet-5"
        assert resp.prompt_tokens == 10
        assert resp.completion_tokens == 5

    def test_is_error_raises_backend_unavailable(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/claude")
        from dev_guardian.harness.backends.claude_cli_backend import ClaudeCLIBackend

        backend = ClaudeCLIBackend()
        monkeypatch.setattr(
            subprocess, "run", _fake_run({"is_error": True, "result": "boom"})
        )

        with pytest.raises(BackendUnavailableError):
            backend.complete(ChatRequest(system="sys", user="hi"))

    def test_nonzero_exit_raises_backend_unavailable(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/claude")
        from dev_guardian.harness.backends.claude_cli_backend import ClaudeCLIBackend

        backend = ClaudeCLIBackend()
        monkeypatch.setattr(subprocess, "run", _fake_run("", returncode=1))

        with pytest.raises(BackendUnavailableError):
            backend.complete(ChatRequest(system="sys", user="hi"))

    def test_non_json_stdout_raises_backend_unavailable(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/claude")
        from dev_guardian.harness.backends.claude_cli_backend import ClaudeCLIBackend

        backend = ClaudeCLIBackend()
        monkeypatch.setattr(subprocess, "run", _fake_run("not json"))

        with pytest.raises(BackendUnavailableError):
            backend.complete(ChatRequest(system="sys", user="hi"))

    def test_response_schema_appends_json_only_instruction(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/claude")
        from dev_guardian.harness.backends.claude_cli_backend import ClaudeCLIBackend

        backend = ClaudeCLIBackend()
        captured = {}

        def _run(cmd, **kwargs):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(
                cmd, 0, stdout=json.dumps({"is_error": False, "result": "{}"}), stderr=""
            )

        monkeypatch.setattr(subprocess, "run", _run)
        backend.complete(
            ChatRequest(system="sys", user="hi", response_schema={"type": "object"})
        )

        system_idx = captured["cmd"].index("--system-prompt") + 1
        assert "JSON" in captured["cmd"][system_idx]
