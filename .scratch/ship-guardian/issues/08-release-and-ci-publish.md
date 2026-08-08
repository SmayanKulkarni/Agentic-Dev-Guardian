# Release policy and CI publish job

Type: grilling
Status: resolved
Blocked by: 02, 03

## Question

CI runs tests but never publishes. What is the release process?

- What triggers a publish — a git tag, a GitHub Release, or a manual dispatch?
- Which of the existing CI jobs gate the publish? The integration job is `continue-on-error: true`
  and the mypy step is too, so neither currently gates anything.
- Version scheme with `hatch-vcs`, and whether a `0.1.0` first release or a `0.x` pre-release train.
- Does a smoke test belong in the pipeline — install the built wheel in a clean environment and run
  `guardian version` — so a broken wheel (see the prompt-asset risk in 03) can't reach PyPI?
- **Console script name.** From ticket 02: PyPI already has a `guardian` package that installs a
  `guardian` console script. Keep the collision (harmless under `uvx`, a real conflict under
  `pipx install`) or rename to `dev-guardian`? Decide before the README and the MCP config in
  ticket 07 are written, since a rename touches both.
- Does the repo need a LICENSE file? `pyproject.toml` declares MIT but no license file was found at the root.

## Answer

Implemented as `.github/workflows/release.yml`.

**Trigger**: pushing an annotated tag `vX.Y.Z`. Not a GitHub Release (that would need the
release created before the artifacts are known good), not a manual dispatch (nothing to
identify the version by). hatch-vcs derives the version from the tag, and `fetch-depth: 0` is
set everywhere it matters, since a shallow clone hides tags and silently yields `0.1.dev0`.

**Gates**, each blocking the next: ruff + unit tests (including the MCP stdio contract test,
which needs no services) → build sdist+wheel → a version guard that refuses any name containing
`.dev` or `+` → a smoke job that installs the wheel into a clean venv, runs `dev-guardian version`,
and asserts the packaged prompts resolve from site-packages. That last check is exactly the
ticket 03 failure mode, and it is the reason the smoke job exists. The existing
`continue-on-error` integration job stays out of the release path entirely.

**Version scheme**: `0.x` pre-release train starting at `v0.1.0`. Provider selection, the
first-run contract and the MCP surface are all one release old; `1.0.0` should wait until the
MCP lifecycle is confirmed against real clients (ticket 07).

**Publishing**: PyPI Trusted Publishing via OIDC (`permissions: id-token: write`), with a
`pypi` GitHub environment so a publish can require manual approval. Nothing to rotate. Set up
the pending publisher on PyPI before the first tag — see ticket 02.

**Console script**: renamed `guardian` → `dev-guardian`. PyPI's existing unrelated `guardian`
package installs a script of the same name, and under `pipx`/`pip` the last install wins
silently. The rename costs one docs pass now instead of an unreproducible bug report later.

**LICENSE**: added at the repo root (MIT, matching `pyproject.toml`), symlinked as
`backend/LICENSE` and declared via `license-files` so the wheel carries it in
`dist-info/licenses/` — a `../LICENSE` path escaped the dist-info directory and was rejected.
