"""
Test for the `guardian://docs-status/{path}` MCP resource (ticket 6).

Follows the existing pattern for `guardian://status`/`guardian://security-policy`:
call the underlying resource function directly, no live MCP session.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from dev_guardian.mcp_server import get_docs_status


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


def test_returns_json_matching_staleness_fields(repo: Path) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    (repo / "GUARDIAN_WIKI.md").write_text(f"# Wiki\n<!-- guardian:commit={head} -->\n")

    raw = get_docs_status(str(repo))
    data = json.loads(raw)

    assert data == {
        "stale": False,
        "commits_behind": 0,
        "recorded_sha": head,
        "head_sha": head,
    }


def test_reflects_stale_state(repo: Path) -> None:
    recorded = _git(repo, "rev-parse", "HEAD")
    (repo / "GUARDIAN_WIKI.md").write_text(f"# Wiki\n<!-- guardian:commit={recorded} -->\n")
    (repo / "a.txt").write_text("two\n")
    _git(repo, "commit", "-q", "-am", "second")
    head = _git(repo, "rev-parse", "HEAD")

    data = json.loads(get_docs_status(str(repo)))

    assert data["stale"] is True
    assert data["commits_behind"] == 1
    assert data["recorded_sha"] == recorded
    assert data["head_sha"] == head


def test_missing_wiki_returns_error_json_instead_of_raising(repo: Path) -> None:
    data = json.loads(get_docs_status(str(repo)))

    assert "error" in data
    assert "dev-guardian docs" in data["error"]
