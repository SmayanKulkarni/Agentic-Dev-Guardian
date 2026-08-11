"""
Unit tests for the shared docs-staleness function (ticket 5).

Uses a real throwaway git repo (via subprocess) rather than mocking git,
per the spec's "test only external behavior" decision.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dev_guardian.docs.staleness import StalenessCheckError, check_staleness


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


def _write_wiki(repo: Path, sha: str) -> Path:
    wiki_path = repo / "GUARDIAN_WIKI.md"
    wiki_path.write_text(f"# Wiki\n<!-- guardian:commit={sha} -->\n")
    return wiki_path


def test_fresh_when_recorded_sha_matches_head(repo: Path) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    wiki_path = _write_wiki(repo, head)

    result = check_staleness(repo, wiki_path)

    assert result.stale is False
    assert result.commits_behind == 0
    assert result.recorded_sha == head
    assert result.head_sha == head


def test_stale_reports_correct_commits_behind(repo: Path) -> None:
    recorded_sha = _git(repo, "rev-parse", "HEAD")
    wiki_path = _write_wiki(repo, recorded_sha)

    for i in range(3):
        (repo / "a.txt").write_text(f"change {i}\n")
        _git(repo, "commit", "-q", "-am", f"change {i}")

    head = _git(repo, "rev-parse", "HEAD")
    result = check_staleness(repo, wiki_path)

    assert result.stale is True
    assert result.commits_behind == 3
    assert result.recorded_sha == recorded_sha
    assert result.head_sha == head


def test_missing_wiki_raises_clear_error(repo: Path) -> None:
    wiki_path = repo / "GUARDIAN_WIKI.md"

    with pytest.raises(StalenessCheckError, match="dev-guardian docs"):
        check_staleness(repo, wiki_path)


def test_wiki_without_marker_raises_clear_error(repo: Path) -> None:
    wiki_path = repo / "GUARDIAN_WIKI.md"
    wiki_path.write_text("# Wiki\nNo marker here.\n")

    with pytest.raises(StalenessCheckError, match="guardian:commit"):
        check_staleness(repo, wiki_path)
