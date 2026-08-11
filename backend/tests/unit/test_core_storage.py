"""Where the embedded stores put their files, and what happens when they are locked."""
from __future__ import annotations

import pytest

from dev_guardian.core.storage import (
    StoreBusyError,
    busy_store,
    guardian_data_dir,
)


def test_explicit_repo_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("GUARDIAN_REPO", str(tmp_path / "from_env"))

    assert guardian_data_dir(tmp_path) == tmp_path / ".guardian"


def test_env_var_used_when_no_argument(tmp_path, monkeypatch):
    monkeypatch.setenv("GUARDIAN_REPO", str(tmp_path))

    assert guardian_data_dir() == tmp_path / ".guardian"


def test_cwd_used_when_nothing_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("GUARDIAN_REPO", raising=False)
    monkeypatch.chdir(tmp_path)

    assert guardian_data_dir() == tmp_path.resolve() / ".guardian"


def test_directory_is_created(tmp_path):
    result = guardian_data_dir(tmp_path)

    assert result.is_dir()


def test_lock_error_becomes_store_busy_error(tmp_path):
    with pytest.raises(StoreBusyError) as exc:
        with busy_store(str(tmp_path)):
            raise RuntimeError("IO exception: Could not set lock on file : /x/kuzu")

    assert "another process" in str(exc.value)


def test_qdrant_lock_message_also_recognised(tmp_path):
    with pytest.raises(StoreBusyError):
        with busy_store(str(tmp_path)):
            raise RuntimeError(
                "Storage folder /x/qdrant is already accessed by another instance "
                "of Qdrant client."
            )


def test_unrelated_runtime_error_passes_through(tmp_path):
    with pytest.raises(RuntimeError) as exc:
        with busy_store(str(tmp_path)):
            raise RuntimeError("something else entirely")

    assert not isinstance(exc.value, StoreBusyError)


def test_settings_no_longer_carry_service_endpoints():
    """The embedded stores have no host/port surface to configure."""
    from dev_guardian.core.config import GuardianSettings

    fields = set(GuardianSettings.model_fields)

    assert not fields & {
        "memgraph_host",
        "memgraph_port",
        "qdrant_host",
        "qdrant_port",
    }


def test_infra_module_is_gone():
    import importlib

    import pytest

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("dev_guardian.core.infra")
