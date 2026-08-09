"""
Infrastructure bootstrap — Memgraph + Qdrant lifecycle for a first run.

Contract (ticket 05):
  * `dev-guardian init` is the *only* thing that starts containers. Every other
    command performs a cheap readiness probe and tells the user to run
    `dev-guardian init` when the services are down. Nothing auto-starts Docker
    behind an MCP stdio session, where there is no terminal to prompt on.
  * No compose file ships. Two `docker run` invocations with fixed container
    names is fewer moving parts than shipping and locating a compose asset,
    and does not require the compose plugin to be installed.
  * "Healthy" is a real probe — a Bolt TCP connect for Memgraph, an HTTP
    `/readyz` for Qdrant — polled until a deadline, never a sleep.
  * A service already answering on its port is reused, whoever started it.
  * Guardian only ever stops containers it created (matched by name), and
    only when the user explicitly asks via `dev-guardian down`.

All human-facing output goes to stderr so it can never corrupt an MCP stdio
stream sharing the process.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from dev_guardian.core.config import get_settings

MEMGRAPH_CONTAINER = "guardian-memgraph"
QDRANT_CONTAINER = "guardian-qdrant"

MEMGRAPH_IMAGE = "memgraph/memgraph-mage:latest"
QDRANT_IMAGE = "qdrant/qdrant:latest"

READY_TIMEOUT_SECONDS = 90.0
_POLL_INTERVAL_SECONDS = 1.0
_PROBE_TIMEOUT_SECONDS = 2.0


class InfraError(RuntimeError):
    """Bootstrap could not reach a healthy state. Message is user-facing."""


@dataclass(frozen=True)
class ServiceStatus:
    name: str
    host: str
    port: int
    ready: bool


def _echo(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


# ── Readiness probes ─────────────────────────────────────────────────────────

def _tcp_ready(host: str, port: int) -> bool:
    """True when something accepts a TCP connection on host:port."""
    try:
        with socket.create_connection((host, port), timeout=_PROBE_TIMEOUT_SECONDS):
            return True
    except OSError:
        return False


def _qdrant_ready(host: str, port: int) -> bool:
    """True when Qdrant answers its readiness endpoint with 2xx."""
    url = f"http://{host}:{port}/readyz"
    try:
        with urllib.request.urlopen(url, timeout=_PROBE_TIMEOUT_SECONDS) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, OSError):
        return False


def probe() -> list[ServiceStatus]:
    """Probe both services once. No side effects."""
    s = get_settings()
    return [
        ServiceStatus(
            "memgraph", s.memgraph_host, s.memgraph_port,
            _tcp_ready(s.memgraph_host, s.memgraph_port),
        ),
        ServiceStatus(
            "qdrant", s.qdrant_host, s.qdrant_port,
            _qdrant_ready(s.qdrant_host, s.qdrant_port),
        ),
    ]


def require_ready() -> None:
    """
    Raise InfraError unless both services answer. Called by every command
    that touches the graph or the vector store.
    """
    down = [s for s in probe() if not s.ready]
    if not down:
        return
    detail = ", ".join(f"{s.name} ({s.host}:{s.port})" for s in down)
    raise InfraError(
        f"Guardian's backing services are not reachable: {detail}.\n"
        "Run `dev-guardian init` to start them, or point GUARDIAN_MEMGRAPH_HOST / "
        "GUARDIAN_QDRANT_HOST at instances you already run."
    )


# ── Docker ───────────────────────────────────────────────────────────────────

def _docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=False
    )


def _docker_available() -> bool:
    return _docker_unavailable_reason() is None


def _docker_unavailable_reason() -> str | None:
    """None when Docker is usable, else a user-facing sentence saying why.

    "Not installed" and "installed but you lack permission on the socket" are
    different problems with different fixes; telling a user in the `docker`
    group's blind spot to go install Docker sends them the wrong way.
    """
    try:
        res = _docker("info")
    except FileNotFoundError:
        return (
            "Docker is not installed or not on PATH. Install it "
            "(https://docs.docker.com/get-docker/) and rerun `dev-guardian init`."
        )
    if res.returncode == 0:
        return None
    stderr = res.stderr.strip()
    if "permission denied" in stderr.lower():
        return (
            "Docker is installed but this user cannot reach the daemon socket:\n"
            f"  {stderr.splitlines()[-1] if stderr else 'permission denied'}\n"
            "Add yourself to the docker group and start a new login session:\n"
            "  sudo usermod -aG docker $USER   # then log out and back in\n"
            "Or rerun `dev-guardian init` as a user that can reach Docker."
        )
    return (
        "Docker is installed but not responding: "
        + (stderr.splitlines()[-1] if stderr else f"`docker info` exited {res.returncode}")
        + "\nStart the Docker daemon and rerun `dev-guardian init`."
    )


def _container_state(name: str) -> str:
    """'running', 'exited', ... or '' when no such container exists."""
    res = _docker("inspect", "-f", "{{.State.Status}}", name)
    return res.stdout.strip() if res.returncode == 0 else ""


def _start_container(name: str, image: str, ports: list[str]) -> None:
    state = _container_state(name)
    if state == "running":
        return
    if state:  # exists but stopped
        res = _docker("start", name)
        if res.returncode != 0:
            raise InfraError(f"Could not start existing container {name}: {res.stderr.strip()}")
        return

    args = ["run", "-d", "--name", name, "--restart", "unless-stopped"]
    for mapping in ports:
        args += ["-p", mapping]
    args.append(image)
    res = _docker(*args)
    if res.returncode != 0:
        raise InfraError(f"`docker run {image}` failed: {res.stderr.strip()}")


def _wait_ready(check, label: str, deadline: float) -> None:
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(_POLL_INTERVAL_SECONDS)
    raise InfraError(
        f"{label} did not become ready within {READY_TIMEOUT_SECONDS:.0f}s. "
        f"Check `docker logs guardian-{label.lower()}`."
    )


def bootstrap(timeout: float = READY_TIMEOUT_SECONDS) -> list[ServiceStatus]:
    """
    Bring Memgraph and Qdrant to a ready state, starting containers only for
    the services that are not already answering.

    Returns the final status of both services.

    Raises:
        InfraError: Docker is unavailable, a container failed to start, or a
            service did not become ready before the timeout.
    """
    settings = get_settings()
    statuses = probe()
    missing = [s for s in statuses if not s.ready]

    for s in statuses:
        if s.ready:
            _echo(f"✓ {s.name} already reachable at {s.host}:{s.port} — reusing.")

    if not missing:
        return statuses

    reason = _docker_unavailable_reason()
    if reason is not None:
        raise InfraError(
            "These services are not reachable: "
            + ", ".join(f"{s.name} ({s.host}:{s.port})" for s in missing)
            + ", and Guardian cannot start them.\n"
            + reason
            + "\nAlternatively, run Memgraph and Qdrant yourself and point "
            "GUARDIAN_MEMGRAPH_HOST / GUARDIAN_QDRANT_HOST at them."
        )

    deadline = time.monotonic() + timeout
    for s in missing:
        if s.name == "memgraph":
            _echo(f"→ starting {MEMGRAPH_CONTAINER} ({MEMGRAPH_IMAGE})...")
            _start_container(
                MEMGRAPH_CONTAINER, MEMGRAPH_IMAGE,
                [f"{settings.memgraph_port}:7687", "7444:7444"],
            )
        else:
            _echo(f"→ starting {QDRANT_CONTAINER} ({QDRANT_IMAGE})...")
            _start_container(
                QDRANT_CONTAINER, QDRANT_IMAGE,
                [f"{settings.qdrant_port}:6333", "6334:6334"],
            )

    for s in missing:
        if s.name == "memgraph":
            _wait_ready(
                lambda: _tcp_ready(settings.memgraph_host, settings.memgraph_port),
                "Memgraph", deadline,
            )
        else:
            _wait_ready(
                lambda: _qdrant_ready(settings.qdrant_host, settings.qdrant_port),
                "Qdrant", deadline,
            )
        _echo(f"✓ {s.name} ready.")

    return probe()


def teardown() -> list[str]:
    """
    Stop the containers Guardian started. Containers it did not create are
    left alone. Returns the names actually stopped.
    """
    if not _docker_available():
        raise InfraError("Docker is not available, so there is nothing to stop.")
    stopped = []
    for name in (MEMGRAPH_CONTAINER, QDRANT_CONTAINER):
        if _container_state(name) == "running":
            _docker("stop", name)
            stopped.append(name)
    return stopped
