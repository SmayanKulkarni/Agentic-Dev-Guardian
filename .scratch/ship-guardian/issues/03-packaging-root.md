# Where does the installable package root live?

Type: prototype
Status: resolved

## Question

`pyproject.toml` sits at `backend/`, not the repo root. That is fine for PyPI (the sdist is built
from `backend/`) but breaks the common `uvx --from git+https://github.com/...` install path, which
expects a project at the repo root.

Prototype the actual install and decide:

- Does `uvx --from git+<repo> guardian version` work as-is? Verify, don't assume.
- Move `pyproject.toml` to the repo root, add a root-level shim, or accept `--from git+<repo>#subdirectory=backend`?
- Does the `dev_guardian` package correctly include the non-Python assets it needs at runtime —
  `prompts/*.yaml` (currently at `backend/prompts/`, *outside* `src/dev_guardian/`) and
  `docker-compose.yml`? `[tool.hatch.build.targets.wheel] packages = ["src/dev_guardian"]` suggests
  both are currently excluded from the wheel, which would break `prompt_registry.py` on an installed copy.

The prompt-asset question is the sharp one: if prompts don't ship, nothing works when installed.

Blocks: 07, 08.

## Answer

**Verified by actually building and installing, not assumed.** Copied the repo to a scratch dir,
git-init'd it, tagged it, and ran `python -m build --wheel` from `backend/` against the pyproject
as it stands today. It fails, twice, before packaging is even a question:

1. `hatch-vcs` can't derive a version: `backend/` is not itself a git repo and `pyproject.toml`
   doesn't tell it to search upward, so `LookupError: setuptools-scm was unable to detect version`.
2. `readme = "README.md"` is resolved relative to `backend/`, where no `README.md` exists — it
   only lives at the repo root. Build fails with `OSError: Readme file does not exist`.

Both are fixed with two lines, no file moves:

```toml
readme = "../README.md"
...
[tool.hatch.version]
source = "vcs"
raw-options = { root = ".." }
```

With that, the wheel builds and `hatch-vcs` correctly derives `0.1.1.dev0+g<sha>` from the parent
repo's tag. **Verdict on the three options: neither "move pyproject.toml to root" nor a root-level
shim is needed — `raw-options.root = ".."` is the one-line fix**, and it also makes
`uvx --from git+<repo>#subdirectory=backend` viable, since `uv`/`pip` already support installing
from a subdirectory of a git checkout.

**The prompt-asset question was the sharp one, and it confirmed the worst case.** Built the wheel
as configured (`packages = ["src/dev_guardian"]`, prompts left at `backend/prompts/`, outside that
tree) and inspected it: zero `.yaml` files shipped. Then actually computed what
`prompt_registry.py`'s `_DEFAULT_ROOT = Path(__file__).parents[4] / "prompts"` resolves to once
installed into `site-packages` — `<venv>/lib/prompts`, which doesn't exist. `PromptRegistry`
doesn't error at construction when the root is missing (`_ensure_loaded` just marks itself loaded
with an empty cache), so the failure is deferred to the first prompt lookup, as a
`PromptNotFoundError` with no hint that the real problem is packaging.

**This isn't only an install-time bug — it's already wrong for a plain source checkout.** Ran the
same path math against `backend/src/dev_guardian/harness/prompt_registry.py` in place:
`parents[4]` from that file is the *repo root* (`Agentic/`), not `backend/`, so `_DEFAULT_ROOT`
today points at `Agentic/prompts` — a directory that has never existed. It works only in tests,
which all pass an explicit `root=` override (`test_harness_prompt_registry.py`). Nothing exercises
the default path. This is a live bug independent of packaging and should be filed/fixed regardless
of ticket 03's outcome.

**Fix, verified end-to-end:** move `backend/prompts/` to `backend/src/dev_guardian/prompts/` and
change `_DEFAULT_ROOT` to `Path(__file__).parent / "prompts"`. Rejected a `force-include` wheel
mapping (tried it, works, adds a `[tool.hatch.build.targets.wheel.force-include]` entry) in favor
of the physical move: `Path(__file__).parent` resolves identically whether the code is running from
a source checkout or from `site-packages`, so there's no dev/installed divergence to maintain, and
`packages = ["src/dev_guardian"]` already ships it with no extra config. This also naturally
satisfies the old `.agents/rules.md` "prompts must live in `backend/prompts/`" constraint's *intent*
(prompts version-controlled alongside the code that loads them) — that rules file no longer exists
in the repo, so it doesn't block the move.

**`docker-compose.yml` does not need to ship.** Grepped `backend/src` for any reference to it —
none. Nothing at runtime reads the compose file today; it's a dev-convenience artifact. Whether it
needs to be embedded (e.g. as a string constant for `docker run`-style bootstrap) is ticket 05's
call once the bootstrap mechanism is designed, not a packaging concern now.

**Action items for whoever implements this:**
- `backend/pyproject.toml`: add `raw-options = { root = ".." }` under `[tool.hatch.version]`,
  change `readme` to `"../README.md"`.
- Move `backend/prompts/*.yaml` → `backend/src/dev_guardian/prompts/*.yaml`.
- `prompt_registry.py`: `_DEFAULT_ROOT = Path(__file__).parent / "prompts"`.
- Update the two references to `backend/prompts/` in the module docstring.

## Implementation status: done

- `backend/pyproject.toml`: `readme = "../README.md"`, `raw-options = { root = ".." }`.
- `backend/prompts/` moved to `backend/src/dev_guardian/prompts/`.
- `prompt_registry.py`: `_DEFAULT_ROOT = Path(__file__).parents[1] / "prompts"`
  (`parents[1]`, not `parent` — the registry module lives one level down, in `harness/`).
- The two prompt-registry tests that swallowed failure with `pytest.skip` now assert, plus a
  new `test_default_root_ships_inside_the_package` that fails if the packaging contract breaks.

Verified: wheel and sdist both build; the wheel carries all 11 `dev_guardian/prompts/*.yaml`;
extracting it to a bare directory and importing from there resolves `gatekeeper` and lists 11
prompts. The release workflow repeats that check on a clean venv install (ticket 08).
