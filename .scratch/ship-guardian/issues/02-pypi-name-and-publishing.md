# PyPI name availability and publishing mechanism

Type: research
Status: resolved

## Question

`uvx <something>` requires the package to be resolvable.

- Is `agentic-dev-guardian` available on PyPI? If not, what is the name?
- What does the console-script name (`guardian`) collide with, if anything, on a user's PATH?
- Trusted Publishing (OIDC, no long-lived token in CI) vs an API token secret — what does the
  GitHub Actions publish job need, and what has to be configured on PyPI first?
- `hatch-vcs` derives the version from git tags. What is the minimum tagging discipline needed
  for a publish job to produce a non-dev version?

Answer feeds the release policy in ticket 08.

## Answer

**`agentic-dev-guardian` is available.** `https://pypi.org/pypi/agentic-dev-guardian/json` returns
404, so the distribution name in `pyproject.toml` needs no change. The name is *not* reserved until
first publish (see pending-publisher caveat below).

**The `guardian` console script collides.** A package named `guardian` already exists on PyPI — a
service-status monitor — and it installs a console script called exactly `guardian`. Two tools
installed into the same environment or the same `~/.local/bin` will fight over the name, and
whichever was installed last wins silently. `[project.scripts]` currently declares
`guardian = "dev_guardian.cli:app"`.

This is a decision, not just a fact, and it belongs to ticket 08: keep `guardian` and accept the
collision, or rename the entry point (`dev-guardian` is the obvious candidate — it matches the
package). Renaming touches the README, all docs, and the MCP client config in ticket 07, so it is
cheapest to decide before any of those are written. Note `uvx` sidesteps the issue for the MCP use
case — it runs in an ephemeral env — but `pipx install` does not.

**Trusted Publishing works for a project that doesn't exist yet, via a "pending publisher":**

- Configured from the PyPI **account** sidebar, not a project sidebar, since there is no project.
- Fields: repository owner, repository name, workflow filename, plus the intended PyPI project
  name. A GitHub Actions **environment** name is optional but strongly recommended — it allows
  requiring manual approval from a trusted subset of maintainers on each publish run.
- A pending publisher does **not** reserve the name. The first successful publish creates the
  project and converts the pending publisher into a normal one. If someone else registers
  `agentic-dev-guardian` in the meantime, the pending publisher is invalidated.
- The workflow exchanges an OIDC token for a short-lived PyPI token, so no long-lived secret is
  stored. The publishing job needs `permissions: id-token: write`.

Recommendation: pending Trusted Publisher over an API token. No secret to rotate or leak, and it
costs one form on PyPI.

**hatch-vcs tagging discipline**: version is derived from git tags, so an untagged build produces a
dev version with a local segment (`+g<sha>`). **PyPI rejects local version segments outright**, so an
untagged publish fails at upload rather than producing a bad release. Minimum discipline: publish
only from an annotated tag (`v0.1.0`) on the commit being released, with `fetch-depth: 0` in the
checkout step — the default shallow clone hides tags from hatch-vcs and yields a `0.1.dev0`-style
version.

Sources:
- [PyPI: adding a trusted publisher](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
- [PyPI: creating a project through OIDC](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
