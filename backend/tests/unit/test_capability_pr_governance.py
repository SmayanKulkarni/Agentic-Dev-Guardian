"""
Unit tests for the raise_github_issue tool in the pr_governance
capability cluster. Stubs the `gh` CLI with a fake executable on PATH
instead of mocking subprocess, per the "test only external behavior"
convention used for git in test_docs_staleness.py.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from dev_guardian.capability_clusters.pr_governance import (
    CLUSTER_REGISTRY,
    _raise_github_issue,
)


def _install_fake_gh(bin_dir: Path, script: str) -> None:
    gh_path = bin_dir / "gh"
    gh_path.write_text(script)
    gh_path.chmod(gh_path.stat().st_mode | stat.S_IEXEC)


def test_raise_github_issue_returns_issue_url_on_success(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _install_fake_gh(
        bin_dir,
        "#!/bin/sh\n"
        'echo "https://github.com/acme/widgets/issues/42"\n'
        "exit 0\n",
    )
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")

    result = json.loads(
        _raise_github_issue(
            title="Gatekeeper rejected PR #7",
            body="Architectural violation detected.",
            repo_path=str(tmp_path),
        )
    )

    assert result == {"issue_url": "https://github.com/acme/widgets/issues/42"}


def test_raise_github_issue_passes_title_body_and_labels_to_gh(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "gh-args.log"
    _install_fake_gh(
        bin_dir,
        "#!/bin/sh\n"
        f'echo "$@" > {log_path}\n'
        'echo "https://github.com/acme/widgets/issues/1"\n'
        "exit 0\n",
    )
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")

    _raise_github_issue(
        title="Red Team flagged missing test",
        body="No coverage for the new branch.",
        repo_path=str(tmp_path),
        labels="guardian:auto",
    )

    logged_args = log_path.read_text()
    assert "issue create" in logged_args
    assert "--title Red Team flagged missing test" in logged_args
    assert "--body No coverage for the new branch." in logged_args
    assert "--label guardian:auto" in logged_args


def test_raise_github_issue_returns_error_json_on_gh_failure(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _install_fake_gh(
        bin_dir,
        "#!/bin/sh\n"
        'echo "not a git repository" 1>&2\n'
        "exit 1\n",
    )
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")

    result = json.loads(
        _raise_github_issue(
            title="x",
            body="y",
            repo_path=str(tmp_path),
        )
    )

    assert "error" in result
    assert "[Guardian Error]" in result["error"]
    assert "not a git repository" in result["error"]


def test_raise_github_issue_returns_error_json_when_gh_not_installed(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    (tmp_path / "empty-bin").mkdir()

    result = json.loads(
        _raise_github_issue(
            title="x",
            body="y",
            repo_path=str(tmp_path),
        )
    )

    assert "error" in result
    assert "gh CLI not found" in result["error"]


def test_pr_governance_cluster_registers_raise_github_issue_tool():
    tools = CLUSTER_REGISTRY["pr_governance"]["tools"]
    assert "raise_github_issue" in tools
    assert tools["raise_github_issue"] is _raise_github_issue
