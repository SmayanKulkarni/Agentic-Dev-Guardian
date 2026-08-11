# Release Runbook — v0.1.0

Everything standing between the current working tree and `uvx --from agentic-dev-guardian dev-guardian serve`
working for a stranger. Ordered. Steps 1–2 are prerequisites; 3–5 are one-time account setup;
6–8 are the release itself.

---

## 0. Security — do this first, before anything is pushed

Your git remote has a GitHub Personal Access Token embedded in the URL:

```
https://SmayanKulkarni:ghp_…@github.com/SmayanKulkarni/Agentic-Dev-Guardian.git
```

It sits in `.git/config` in plaintext, and any `git remote -v` output — including screen shares,
pasted logs, and backups — leaks it. It grants whatever scopes you gave it on your whole account.

1. Revoke it: <https://github.com/settings/tokens> → find the token → **Delete**.
2. Strip it from the remote:

```bash
git remote set-url origin https://github.com/SmayanKulkarni/Agentic-Dev-Guardian.git
```

3. Authenticate properly instead (stores a credential in the OS helper, not in the repo):

```bash
gh auth login          # choose HTTPS, authenticate in browser
gh auth setup-git
git remote -v          # confirm: no `ghp_` anywhere
```

If the token was ever pushed in a *file* (not just `.git/config`), it is in the GitHub history and
revoking is the only fix — rewriting history does not un-leak it. `.git/config` is not pushed, so
revoke + set-url is sufficient here.

---

## 1. Tidy `.gitignore` before the first big commit

These are currently untracked *and* not ignored, so a `git add -A` would commit them:
`.scratch/`, `graphify-out/`, `backend/.coverage`, `.pytest_cache/`.

`.scratch/ship-guardian/` is the decision record for this whole release — it is worth keeping in
the repo. The rest is not.

```bash
cat >> .gitignore <<'EOF'

# Test / coverage artifacts
.coverage
.pytest_cache/
htmlcov/

# Tool output
graphify-out/
.code-review-graph/
EOF
```

Then check nothing unwanted is staged:

```bash
git add -A
git status --short        # read every line before committing
```

---

## 2. Commit the work

The tree currently holds the entire harness migration, the ship-guardian tickets, and the
optional-tracing + MCP-caching work. Split it or land it as one — but land it before tagging,
because hatch-vcs derives the version from the tagged commit.

```bash
git checkout -b release/v0.1.0

git commit -m "feat: ship-guardian release prep — packaging, providers, MCP lifecycle

Implements tickets 01-09 (see .scratch/ship-guardian/):
- provider selection via GUARDIAN_PROVIDER across 6 backends
- packaging fixes so prompts ship inside the wheel
- first-run contract: dev-guardian init bootstraps Memgraph + Qdrant
- MCP stdio contract test, console script renamed to dev-guardian

Plus: langfuse demoted to the [tracing] extra behind a no-op shim, and
GraphRAG clients cached per-process so MCP tool calls stop reloading the
fastembed ONNX model on every request."

git push -u origin release/v0.1.0
```

Open a PR and let CI (`.github/workflows/ci.yml`) go green, then merge to `main`.

**Do not tag from the branch.** Tag the commit on `main` that you actually want published.

---

## 3. Verify the release gates locally (cheap, catches the expensive failures)

```bash
cd backend
ruff check src/ tests/
pytest tests/unit/ tests/integration/test_mcp_client_contract.py -m "not integration and not llm"
python -m build --outdir /tmp/dist
```

Then reproduce the smoke job — this is the one that catches the packaging failure mode
(prompts not shipping inside the wheel):

```bash
python -m venv /tmp/smoke
/tmp/smoke/bin/pip install /tmp/dist/*.whl
/tmp/smoke/bin/dev-guardian version
/tmp/smoke/bin/python -c "
from dev_guardian.harness.prompt_registry import PromptRegistry
ids = PromptRegistry().list(); assert 'gatekeeper' in ids; print('prompts ok:', len(ids))"
```

All three must pass. `release.yml` runs the same checks and will refuse to publish otherwise.

---

## 4. Create the PyPI pending Trusted Publisher

There is no PyPI project yet, so this is configured from your **account** sidebar, not a project's.

1. <https://pypi.org/manage/account/publishing/>
2. Fill the **pending publisher** form:

| Field | Value |
|---|---|
| PyPI Project Name | `agentic-dev-guardian` |
| Owner | `SmayanKulkarni` |
| Repository name | `Agentic-Dev-Guardian` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

Caveats worth knowing:

- A pending publisher does **not** reserve the name. `agentic-dev-guardian` was free when
  checked; if someone registers it before your first publish, the pending publisher is
  invalidated and you need a new name.
- The environment name must match step 5 exactly, or the OIDC exchange fails at publish time.
- On first successful publish, the pending publisher converts to a normal one automatically.

---

## 5. Create the `pypi` GitHub environment

This is what makes a publish require your explicit approval instead of firing on any tag push.

1. Repo → **Settings** → **Environments** → **New environment** → name it `pypi`.
2. Under **Deployment protection rules**, tick **Required reviewers** and add yourself.
3. Save. No secrets to add — Trusted Publishing uses a short-lived OIDC token, so there is
   nothing to store or rotate.

---

## 6. Tag and push

The tag must be **annotated** (`-a`). A lightweight tag works for hatch-vcs but conveys no
message, and the release policy assumes annotated.

```bash
git checkout main && git pull
git tag -a v0.1.0 -m "v0.1.0 — first public release"
git push origin v0.1.0
```

Why the version must come from a tag: hatch-vcs derives it from git. An untagged build produces
`0.1.dev8+g82c0020`, and PyPI rejects local version segments (`+...`) outright — so an untagged
publish fails at upload rather than shipping a bad release. `release.yml` sets `fetch-depth: 0`
everywhere it matters, because a shallow clone hides tags and silently yields a dev version.

---

## 7. Approve the publish

1. Repo → **Actions** → the `Release` run triggered by the tag.
2. Watch the gates: `test` → `build` → `smoke`. Each blocks the next.
3. `publish` waits on the `pypi` environment. Click **Review deployments** → **Approve and deploy**.
4. Confirm: <https://pypi.org/project/agentic-dev-guardian/>

---

## 8. Verify the install path a stranger will actually use

From a machine (or container) that has never seen this repo:

```bash
uvx --from agentic-dev-guardian dev-guardian version
uvx --from agentic-dev-guardian dev-guardian mcp-config
```

Then paste that block into Cursor / Claude Desktop and confirm the 4 bootstrap tools appear.
If they do, the release is real.

---

## After the release — optional, in priority order

### Register in MCP directories

Discovery only; all of these point at the PyPI package you just published.

- **Official MCP registry** — needs a `server.json` at the repo root describing the package and
  its env vars, then submission via the registry's publish flow.
- **Smithery**, **PulseMCP**, **Glama** — third-party listings, each with its own submission form.

### Manually confirm the JIT lifecycle per client

`test_mcp_client_contract.py` proves the *server* half: the tool list really does change across
`equip_capability` / `unequip_capability`. What no test can prove is whether a given IDE acts on
`notifications/tools/list_changed` or caches tools for the session. Open each client you care
about, equip a capability, and note whether the new tools appear immediately or on next refresh.
Record the answer in `.scratch/ship-guardian/issues/07-mcp-client-integration.md` — it is the last
open question on the design's core bet.

### Not doing: hosted SaaS

Indexing requires the user's proprietary code on the host. A hosted Guardian would contradict the
project's own data-minimization guarantee, which is why `.scratch/ship-guardian/map.md` puts it out
of scope. `dev-guardian serve --transport streamable-http` is the legitimate substitute: the user
self-hosts one Guardian on the machine that already holds their code.
