# Config and secrets location for an installed copy

Type: grilling
Status: resolved
Blocked by: 04, 05

## Question

`GuardianSettings.Config.env_file = (".env", "backend/.env")` — both paths are relative to the
working directory and assume a source checkout. An installed `uvx` copy has neither.

- Where does user config live? `~/.config/guardian/config.toml`, a user-level `.env`, OS keyring,
  or purely environment variables passed through the MCP client's JSON config?
- MCP clients (Cursor, Claude Desktop) spawn the server with their own `env` block. Is that the
  primary configuration channel, making a config file secondary?
- Precedence order between environment, config file, and per-project overrides.
- What is per-project rather than global? The indexed repo path is per-project; the API key is global.
- Does anything need to be written at all, or can `init` just print the JSON block for the user to paste?

## Answer

Implemented in `backend/src/dev_guardian/core/config.py`.

**Guardian writes nothing.** `dev-guardian init --print-mcp-config` prints the JSON block with
the resolved values filled in, and the user pastes it. No config file to create, no keyring to
integrate, no secret at rest that Guardian is responsible for.

**Environment variables are the primary channel**, because that is what an MCP client gives you:
Cursor / Claude Desktop spawn the server with their own `env` block. Every setting now accepts a
`GUARDIAN_`-prefixed name (`GUARDIAN_GROQ_API_KEY`, `GUARDIAN_MEMGRAPH_HOST`, ...) alongside its
vendor name (`GROQ_API_KEY`, `MEMGRAPH_HOST`), via `AliasChoices`. The prefix disambiguates inside
a shared IDE environment; the bare name keeps existing shell profiles and the CI workflow working.
This matches the already-shipped `GUARDIAN_PROVIDER` / `GUARDIAN_MODEL` convention from ticket 04.

**Precedence**, highest first:
1. real environment variables (the MCP `env` block, or the shell),
2. `./.env` — repo-local,
3. `backend/.env` — checkout-local,
4. `~/.config/guardian/.env` — user-level, the only one that exists for an installed `uvx` copy.

Files 2–4 are convenience; pydantic-settings always lets a real env var win.

**Global vs per-project**: credentials, provider choice and service endpoints are global. The
indexed repository is *not configuration at all* — it is a CLI argument on every command that
takes one, so nothing per-project needs storing.
