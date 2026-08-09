# First-run contract and infra bootstrap

Type: grilling
Status: resolved

## Question

Memgraph and Qdrant must be running before any command works. The chosen approach is auto-bootstrap
via Docker. Pin down the contract.

- What triggers the bootstrap — a dedicated `guardian init`, a lazy check inside every command, or both?
- Guardian ships a `docker-compose.yml` today. Does the installed package carry it, or does the CLI
  issue `docker run` calls directly? (Compose file location interacts with ticket 03's asset question.)
- How is "healthy" determined, and what is the timeout? Memgraph Bolt on 7687 and Qdrant HTTP on 6333
  both need a real readiness probe, not a sleep.
- **Docker absent.** What happens? Clear instructions and exit, or does this promote the embedded-store
  fallback out of the fog?
- Containers already running, or ports already bound by someone else's Memgraph — detect and reuse, or fail?
- Who stops them? Does Guardian ever tear down containers it started?
- `guardian serve` runs as an MCP **stdio** server: the IDE spawns it and stdout is the protocol channel.
  Bootstrap output must not corrupt that stream, and an IDE gives the user nowhere to see a prompt.
  Does bootstrap-on-serve even make sense, or must `init` be a prerequisite the server only verifies?

Blocks: 06.

## Answer

Implemented in `backend/src/dev_guardian/core/infra.py` plus two new CLI commands.

**Trigger**: `guardian init` is the only thing that ever *starts* anything. Every other
command calls `_require_infra()` (`cli.py`), a cheap probe that fails with
`Run \`dev-guardian init\`` when a service is down. Lazy auto-bootstrap inside arbitrary
commands was rejected: an MCP stdio session has no terminal to prompt on and no safe
place to print a 60-second container pull.

**No compose file ships.** Nothing in `backend/src` ever referenced one (ticket 03 confirmed
this), and none exists in the repo today, so there was no asset to package. `init` issues two
`docker run` calls with fixed container names (`guardian-memgraph`, `guardian-qdrant`),
which also avoids requiring the compose plugin.

**Health** is a real probe, polled once a second to a 90s deadline (`--timeout` overrides):
TCP connect on Memgraph's Bolt port, HTTP `GET /readyz` on Qdrant. No sleeps.

**Docker absent**: hard fail with the install link *and* the alternative — point
`GUARDIAN_MEMGRAPH_HOST` / `GUARDIAN_QDRANT_HOST` at instances the user already runs. No
embedded-store fallback: a second storage path would need its own query implementation
for every Cypher call in the codebase.

**Already running / ports bound**: whatever answers the readiness probe is reused, whoever
started it, and `init` says so. Only services that fail the probe get a container started.
A port bound by something that is *not* healthy surfaces as a start failure or a readiness
timeout, both with the container name to check logs on.

**Teardown**: never automatic. `guardian down` stops only the two containers Guardian
creates, matched by name; anything the user started is left alone.

**`serve`**: verifies, never bootstraps. All infra output goes to stderr so it cannot
corrupt the stdio protocol channel, and a failed check exits non-zero so the IDE surfaces
the problem instead of hanging. `init` is a documented prerequisite.

Covered by `backend/tests/unit/test_core_infra.py` (reuse, Docker-absent, partial start,
timeout, selective teardown) with Docker and the probes patched.
