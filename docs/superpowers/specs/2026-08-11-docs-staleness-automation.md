# Spec: Docs Regen Automation + IDE Staleness Signal

## Problem Statement

`GUARDIAN_WIKI.md` is generated on demand (`dev-guardian docs` / the
`generate_architecture_docs` MCP tool) but nothing regenerates it
automatically, and nothing tells a developer or an IDE agent that the wiki
has drifted from the code. After a merge to `main`, the wiki silently goes
stale until someone remembers to re-run docs generation. An IDE agent
answering architecture questions from a stale wiki gives wrong answers with
no indication it should distrust the doc.

## Solution

1. Embed the commit SHA the wiki was generated from directly in
   `GUARDIAN_WIKI.md`, so staleness is computable from the file alone (no
   sidecar state).
2. Add one shared staleness-check function, exposed two ways:
   - An MCP resource (`guardian://docs-status/{path}`) the IDE can query.
   - A CLI subcommand (`dev-guardian docs-status`) a CI job can call.
3. Add a GitHub Action that runs the CLI staleness check on push to `main`
   and fails/comments if the wiki is behind — it does **not** regenerate
   docs itself (that would require standing up Memgraph + Qdrant in CI).
   Regeneration stays a local operation: a developer (or their IDE agent,
   which already has an indexed Memgraph instance) runs `dev-guardian docs`
   and includes the updated `GUARDIAN_WIKI.md` in the same PR. This
   distributes indexing load to developer machines instead of CI runners.
4. Leave it to the IDE agent's own judgment whether to proactively check
   staleness or suggest regen — no forced prompting added to bootstrap tool
   descriptions.

## User Stories

1. As a developer merging a PR, I want CI to fail if I forgot to regenerate
   `GUARDIAN_WIKI.md` after a structural change, so that stale docs never
   land on `main` silently.
2. As a developer, I want the staleness check to run without spinning up
   Memgraph/Qdrant in CI, so that CI stays fast and cheap.
3. As a developer, I want a clear local command to run before pushing, so
   that fixing staleness is a one-command action, not a mystery.
4. As an IDE agent, I want to query a resource that tells me whether the
   wiki is stale and by how many commits, so that I can decide whether to
   trust it when answering architecture questions.
5. As an IDE agent, I want the staleness resource to return machine-readable
   JSON (stale flag, commits-behind count, both SHAs), so that I can reason
   about severity rather than just a boolean.
6. As an IDE agent equipped with `codebase_intelligence`, I want to
   optionally decide on my own to suggest `generate_architecture_docs` to
   the user when I notice staleness, without being forced to interrupt
   every session with a check.
7. As a maintainer, I want the recorded SHA embedded in the wiki file
   itself, so that there's no separate state file that can get out of sync
   with the wiki.
8. As a maintainer, I want one staleness-check function used by both the
   MCP resource and the CI gate, so that the two surfaces can never
   disagree about what "stale" means.
9. As a CI reviewer, I want the Action's failure/comment to say exactly how
   many commits behind the wiki is and what command to run to fix it, so
   that the fix path is obvious without reading the workflow file.
10. As a developer working on a fork/branch without Memgraph running
    locally, I want a clear error (not a silent skip) if I try to run
    `dev-guardian docs-status` without an existing `GUARDIAN_WIKI.md`, so
    that I understand the check requires a first-time doc generation to
    have happened at least once.
11. As a maintainer, I want the GitHub Action to open/require a docs-update
    PR rather than pushing directly to `main`, so that generated content
    still goes through normal review before merge (applies to the local
    developer's own PR containing the regenerated wiki, not a bot-authored
    commit).
12. As a project owner, I want the new capability tracked in the issue
    tracker with the `ready-for-agent` label, so that an agent can pick it
    up and implement it without further triage.

## Implementation Decisions

- **SHA embedding**: `build_wiki` (in `wiki_builder.py`) records
  `git rev-parse HEAD` for `repo_path` into the generated markdown as an
  HTML comment, e.g. `<!-- guardian:commit=<sha> -->`, near the existing
  timestamp/header section. `save_wiki` writes it through unchanged — it's
  part of the markdown body, not separate metadata.
- **Shared staleness function**: one function (naturally sited in
  `wiki_builder.py` given it already owns wiki I/O, or a new
  `docs/staleness.py` module if that keeps the file within the codebase's
  file-size norms) takes `repo_path` and the wiki file path, reads the
  recorded SHA out of the `guardian:commit=` comment, shells `git -C
  repo_path rev-parse HEAD` for the current SHA, and — if they differ —
  shells `git -C repo_path rev-list --count <recorded_sha>..HEAD` for
  commits-behind. Returns a structure with `stale` (bool),
  `commits_behind` (int), `recorded_sha`, `head_sha`. This is the single
  source of truth for "is the wiki stale" — both callers below wrap it,
  neither reimplements it.
- **MCP resource**: new templated resource `guardian://docs-status/{path}`
  in `mcp_server.py`, following the existing plain-resource pattern at
  `guardian://status` / `guardian://security-policy` (`mcp_server.py:253`,
  `:282`) but using the `mcp` library's templated-URI decorator syntax —
  confirm the exact signature against the installed `mcp` SDK version's
  docs before implementing (do not assume Node-SDK-style patterns). Calls
  the shared staleness function and returns its result as a JSON string.
  No instruction is added telling the agent to poll it proactively — usage
  is left to the IDE's judgment, per the resolved open question.
- **CLI subcommand**: new `dev-guardian docs-status <path>` subcommand in
  `cli.py`, alongside the existing `docs` command. Calls the shared
  staleness function, prints a human-readable summary, and exits non-zero
  if stale (so it composes as a CI gate step). If no `GUARDIAN_WIKI.md`
  exists yet at the expected output path, this is an error (exit non-zero
  with a clear message), not a silent pass — first-time generation must
  happen before staleness can be tracked.
- **GitHub Action**: new `.github/workflows/docs-sync.yml`, triggered on
  push to `main` (and PRs targeting `main`, so the gate is visible before
  merge). Installs `agentic-dev-guardian` from PyPI, runs
  `dev-guardian docs-status .` against the repo's own
  `GUARDIAN_WIKI.md`. No Memgraph/Qdrant service containers — this job
  never generates docs, only checks the embedded SHA against `HEAD`. On
  failure, the job output/PR comment states commits-behind and the fix
  command (`dev-guardian docs .` run locally, then commit the result).
- **Regeneration stays local**: no code change needed to make this true —
  `dev-guardian docs` and the `generate_architecture_docs` MCP tool already
  do this, run against a developer's already-indexed local Memgraph. The
  spec just formalizes that CI depends on this having been done rather than
  doing it itself.
- **No bootstrap/tool-description changes**: per the resolved open
  question, `list_capabilities`, `query_guardian_graph`, and the
  `generate_architecture_docs` docstring are left as-is. The docs-status
  resource's own docstring documents what it returns, not when to call it.

## Testing Decisions

- Test only external behavior: given a wiki file with a known embedded SHA
  and a real (or fixture) git repo at a known `HEAD`, the shared staleness
  function returns the correct `stale`/`commits_behind`/SHA fields — not
  how it shells out internally.
- The shared staleness function is the one seam that needs direct unit
  coverage; both the MCP resource wrapper and the CLI subcommand wrapper
  are thin enough to cover via one integration-style test each (resource
  returns valid JSON matching the function's output; CLI exits non-zero on
  a deliberately stale fixture wiki and zero on a fresh one).
- Prior art: MCP resource tests already exercise `guardian://status` /
  `guardian://security-policy` by calling the underlying resource function
  directly rather than spinning up a live MCP session — follow the same
  pattern for `guardian://docs-status/{path}`.
- CLI subcommand tests follow the existing pattern used for the `docs`
  command in the CLI test suite (invoke via the CLI test runner, assert
  exit code and printed output).
- No test needed for the GitHub Action YAML itself beyond it being valid
  workflow syntax — its behavior is just "run this CLI command," which is
  covered by the CLI test.

## Out of Scope

- Auto-committing or auto-opening a docs-update PR from CI — CI only gates,
  it never writes. Regeneration and its PR are authored by whoever pushed
  the change that made docs stale.
- Any mechanism to push a staleness notification to an IDE that isn't
  currently connected (ruled out earlier in the design — MCP is
  stdio-transport, session-scoped).
- Forced/automatic proactive staleness-checking behavior in the IDE agent
  (bootstrap tool descriptions, system-prompt-level nudges) — explicitly
  decided against; usage is left to the IDE agent's judgment.
- CI running Memgraph/Qdrant as service containers, or any artifact-caching
  hybrid to reuse a local index in CI — considered and rejected in favor of
  the local-regen + CI-gate split.
- Historical staleness tracking / dashboards — the check is point-in-time
  only (current HEAD vs recorded SHA).

## Further Notes

This spec resolves two design forks that were left open mid-brainstorm:

1. Whether CI generates docs itself (rejected — too heavy, needs
   Memgraph+Qdrant) vs. gates on a locally-generated wiki (chosen).
2. Whether the docs-status resource should proactively instruct the IDE
   agent to check/suggest regen (rejected — left to IDE judgment, per the
   answered open question in the originating handoff doc).

The originating handoff document
(`/tmp/handoff-guardian-docs-automation-2026-08-11.md`) has the full
prior-session context and can be discarded once this spec and its tracker
issue exist.
