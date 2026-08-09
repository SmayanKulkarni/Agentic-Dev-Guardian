"""
Unit tests for the first-run infra contract (ticket 05).

No Docker and no live services are required: the probes and the docker
shell-out are patched.
"""
from __future__ import annotations

import pytest

from dev_guardian.core import infra


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(infra.time, "sleep", lambda _s: None)


def _patch_probes(monkeypatch, *, memgraph: bool, qdrant: bool) -> None:
    monkeypatch.setattr(infra, "_tcp_ready", lambda host, port: memgraph)
    monkeypatch.setattr(infra, "_qdrant_ready", lambda host, port: qdrant)


class TestProbe:
    def test_reports_both_services_ready(self, monkeypatch):
        _patch_probes(monkeypatch, memgraph=True, qdrant=True)
        assert [s.ready for s in infra.probe()] == [True, True]

    def test_require_ready_passes_when_both_up(self, monkeypatch):
        _patch_probes(monkeypatch, memgraph=True, qdrant=True)
        infra.require_ready()  # must not raise

    def test_require_ready_names_the_down_service(self, monkeypatch):
        _patch_probes(monkeypatch, memgraph=True, qdrant=False)
        with pytest.raises(infra.InfraError) as exc:
            infra.require_ready()
        assert "qdrant" in str(exc.value)
        assert "guardian init" in str(exc.value)


class TestDockerUnavailableReason:
    """The three failure modes must not be collapsed into one message."""

    def _patch_docker(self, monkeypatch, returncode: int, stderr: str) -> None:
        import subprocess

        monkeypatch.setattr(
            infra, "_docker",
            lambda *a: subprocess.CompletedProcess(a, returncode, "", stderr),
        )

    def test_none_when_docker_answers(self, monkeypatch):
        self._patch_docker(monkeypatch, 0, "")
        assert infra._docker_unavailable_reason() is None

    def test_permission_denied_says_docker_group_not_install_docker(self, monkeypatch):
        self._patch_docker(
            monkeypatch, 1,
            "permission denied while trying to connect to the Docker daemon socket",
        )
        reason = infra._docker_unavailable_reason()
        assert "usermod -aG docker" in reason
        assert "get-docker" not in reason  # must not send them to the installer

    def test_missing_binary_says_install(self, monkeypatch):
        def _missing(*_a):
            raise FileNotFoundError

        monkeypatch.setattr(infra, "_docker", _missing)
        assert "get-docker" in infra._docker_unavailable_reason()


class TestBootstrap:
    def test_reuses_already_running_services_without_touching_docker(self, monkeypatch):
        _patch_probes(monkeypatch, memgraph=True, qdrant=True)

        def _boom(*_a, **_k):
            raise AssertionError("docker must not be invoked when services are up")

        monkeypatch.setattr(infra, "_docker", _boom)
        monkeypatch.setattr(infra, "_docker_unavailable_reason", _boom)

        assert all(s.ready for s in infra.bootstrap())

    def test_docker_absent_raises_actionable_error(self, monkeypatch):
        _patch_probes(monkeypatch, memgraph=False, qdrant=False)
        monkeypatch.setattr(
            infra, "_docker_unavailable_reason", lambda: "Docker is not installed."
        )

        with pytest.raises(infra.InfraError) as exc:
            infra.bootstrap()
        msg = str(exc.value)
        assert "Docker is not installed." in msg
        assert "GUARDIAN_MEMGRAPH_HOST" in msg

    def test_starts_only_the_missing_service(self, monkeypatch):
        # Memgraph is up already; only Qdrant should be started.
        monkeypatch.setattr(infra, "_tcp_ready", lambda host, port: True)
        qdrant_states = iter([False, True, True, True])
        monkeypatch.setattr(
            infra, "_qdrant_ready", lambda host, port: next(qdrant_states, True)
        )
        monkeypatch.setattr(infra, "_docker_unavailable_reason", lambda: None)
        started: list[str] = []
        monkeypatch.setattr(
            infra, "_start_container",
            lambda name, image, ports: started.append(name),
        )

        infra.bootstrap(timeout=5)
        assert started == [infra.QDRANT_CONTAINER]

    def test_timeout_when_service_never_becomes_ready(self, monkeypatch):
        _patch_probes(monkeypatch, memgraph=False, qdrant=False)
        monkeypatch.setattr(infra, "_docker_unavailable_reason", lambda: None)
        monkeypatch.setattr(infra, "_start_container", lambda *a, **k: None)

        with pytest.raises(infra.InfraError, match="did not become ready"):
            infra.bootstrap(timeout=0.01)


class TestTeardown:
    def test_stops_only_guardian_containers_that_run(self, monkeypatch):
        monkeypatch.setattr(infra, "_docker_unavailable_reason", lambda: None)
        monkeypatch.setattr(
            infra, "_container_state",
            lambda name: "running" if name == infra.QDRANT_CONTAINER else "",
        )
        calls: list[tuple[str, ...]] = []
        monkeypatch.setattr(infra, "_docker", lambda *a: calls.append(a) or None)

        assert infra.teardown() == [infra.QDRANT_CONTAINER]
        assert calls == [("stop", infra.QDRANT_CONTAINER)]
