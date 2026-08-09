# Map: Ship Guardian as a one-command MCP

## Destination

Anyone can run a single command (`uvx`/`pipx`) and have Agentic Dev Guardian running as an
MCP server in Cursor / Claude Desktop / Windsurf against their own codebase, with any LLM
provider they already have a key for — or a local model. The `guardian` CLI ships alongside
for free. This map is done when every decision blocking that release is made.

## Notes

- **Domain**: Python packaging + distribution, MCP stdio servers, LLM provider abstraction, first-run UX.
- **Skills every session should consult**: `/grilling`, `/domain-modeling`, `ponytail` (laziest path that works), `mcp-server-patterns`, `deployment-patterns`.
- **No subagents.** Research tickets get resolved inline in-session, not dispatched.
- **Standing constraint**: proprietary code never leaves the host. Any provider work must preserve the data-minimisation guarantee (only AST-derived context is sent to an LLM).
- **Repo facts established while charting** (don't re-derive):
  - `pyproject.toml` lives at `backend/`, not the repo root. `[project.scripts] guardian = "dev_guardian.cli:app"`. Version is `hatch-vcs` (needs git tags).
  - `harness/backends/` already has `groq_backend.py`, `anthropic_backend.py`, `openai_backend.py` behind an `LLMBackend` Protocol — but `skill_router.py:192` hardcodes `backend or GroqBackend()`. Provider-agnosticism is half-built.
  - `GUARDIAN_USE_HARNESS` defaults to on across all 9 agent/docs modules; the legacy direct-Groq path is still present behind `=0`.
  - `GuardianSettings` (`core/config.py`) reads `.env` / `backend/.env` only — no user-level config location.
  - Memgraph + Qdrant come from `backend/docker-compose.yml`. No bootstrap, no health check, no doctor command.
  - CLI commands: `index`, `evaluate`, `audit`, `incident`, `refactor`, `docs`, `serve`, `version`. No `init`.
  - CI (`.github/workflows/ci.yml`) runs ruff + mypy + unit tests with a 60% coverage gate on `harness/` and `skills/` only. No publish job.

## Decisions so far

<!-- one line per resolved ticket -->

- [Local LLM / SLM support path](issues/01-local-llm-path.md) — no new adapter needed; local models are `openai_backend.py` with a `base_url` and an optional key, but the JSON verdicts need `response_format` (never sent today by any backend), and the backend-keyed context/rate limits break.
- [PyPI name availability and publishing mechanism](issues/02-pypi-name-and-publishing.md) — `agentic-dev-guardian` is free; publish via a pending Trusted Publisher from an annotated tag with `fetch-depth: 0`; the `guardian` console script name collides with an existing PyPI package.

## Not yet specified

- **Docs rewrite for the new install story.** The README currently documents a from-source, bring-your-own-infra setup. It has to be rewritten once the install command, provider contract, and first-run flow are decided — can't be phrased sharply before then.
- **Failure-mode UX.** What the user sees when Memgraph is down, the API key is wrong, or the model returns unparseable JSON. Depends on the first-run contract.
- **Embedded / no-Docker fallback.** If the first-run contract concludes Docker-absent is a common enough case, an embedded graph store may need revisiting. Explicitly deferred, not ruled out.
- **Windows / macOS support surface.** Docker bootstrap and `.env` paths are Linux-shaped today.
- **Test + coverage bar for release.** Current gate covers only two packages; unclear what the release-worthy bar is.
## Done since the tickets closed

- **Langfuse is now the `[tracing]` extra.** All 13 `from langfuse import observe` sites import from
  `core/tracing.py`, which falls back to a no-op decorator (both `@observe` and `@observe(...)` shapes).
  `test_core_tracing.py` fails if any module re-imports langfuse directly.
- **MCP client caching.** Every MCP tool built a fresh `HybridRetriever()`/`MemgraphClient()` per call,
  and `QdrantCodeClient.__init__` loads the fastembed ONNX model plus a probe embedding — so the server
  paid that on every request. `graphrag/clients.py` holds one `@lru_cache` instance per process, with
  `reset_clients()` on the error paths so a dead connection doesn't stick. Imports are deferred into
  the accessors so the ticket-07 cold-start budget is untouched.
- **`serve --transport streamable-http|sse --host --port`**, loopback-bound. Verified: `initialize`
  over HTTP at `/mcp` returns 200.

## Out of scope

- **Web frontend.** The empty `frontend/` tree (`components/`, `hooks/`, `public/`) implies a UI that does not exist. CLI + MCP is the product surface; the directory gets deleted during release prep. Not part of this effort, and not revisited unless the destination is redrawn.
- **Hosted backend / API service.** Would require proprietary code to leave the host, contradicting the project's core guarantee.
