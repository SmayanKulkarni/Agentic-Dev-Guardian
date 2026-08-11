"""
CLI tests for `dev-guardian docs-status` (ticket 5).

Exercises the real `check_staleness` function against a throwaway git repo
via the Typer CLI runner, asserting exit codes rather than internals.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dev_guardian.cli import app

runner = CliRunner()


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    _git(repo_path, "init", "-q")
    _git(repo_path, "config", "user.email", "test@example.com")
    _git(repo_path, "config", "user.name", "Test")
    (repo_path / "a.txt").write_text("one\n")
    _git(repo_path, "add", "a.txt")
    _git(repo_path, "commit", "-q", "-m", "initial")
    return repo_path


def test_exits_zero_when_fresh(repo: Path) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    (repo / "GUARDIAN_WIKI.md").write_text(f"# Wiki\n<!-- guardian:commit={head} -->\n")

    res = runner.invoke(app, ["docs-status", str(repo)])

    assert res.exit_code == 0
    assert "fresh" in res.stdout.lower()


def test_exits_nonzero_when_stale(repo: Path) -> None:
    recorded = _git(repo, "rev-parse", "HEAD")
    (repo / "GUARDIAN_WIKI.md").write_text(f"# Wiki\n<!-- guardian:commit={recorded} -->\n")
    (repo / "a.txt").write_text("two\n")
    _git(repo, "commit", "-q", "-am", "second")

    res = runner.invoke(app, ["docs-status", str(repo)])

    assert res.exit_code != 0
    combined = res.output + res.stderr
    assert "1 commit" in combined or "stale" in combined.lower()


def test_exits_nonzero_with_clear_message_when_wiki_missing(repo: Path) -> None:
    res = runner.invoke(app, ["docs-status", str(repo)])

    assert res.exit_code != 0
    assert "dev-guardian docs" in (res.output + res.stderr)
