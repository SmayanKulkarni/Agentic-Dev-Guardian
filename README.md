# Agentic Dev Guardian

[![PyPI](https://img.shields.io/pypi/v/agentic-dev-guardian.svg)](https://pypi.org/project/agentic-dev-guardian/)
[![Python](https://img.shields.io/pypi/pyversions/agentic-dev-guardian.svg)](https://pypi.org/project/agentic-dev-guardian/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/SmayanKulkarni/Agentic-Dev-Guardian/blob/main/LICENSE)

> Index your codebase into a knowledge graph, then let agents use it to review PRs, red-team risky functions, triage incidents, plan refactors, and write architecture docs.

**Install:** `pip install agentic-dev-guardian` · **Command:** `dev-guardian` · [Source](https://github.com/SmayanKulkarni/Agentic-Dev-Guardian) · [Issues](https://github.com/SmayanKulkarni/Agentic-Dev-Guardian/issues)

---

## Why

Hand a model a diff and it sees the diff. It misses the twelve callers of the function you
changed, the subclass overriding it, and the module importing it for a side effect.

Guardian indexes your repository into a call, import, and inheritance graph first. Agents
then query that graph for the neighbourhood around each change, so a verdict rests on what
your code references instead of on whatever fit in the context window.

Reach for it when you want:

- **A PR gate that knows the blast radius.** `evaluate` sends a diff through a Mixture-of-Agents pipeline and returns `approve / remediate / reject` with the impacted call graph attached.
- **Hardening before anyone files a PR.** `audit` ranks functions by fan-out and red-teams the worst offenders.
- **On-call help that reads the graph.** `incident --trace` turns a stack trace into a hotfix blueprint using the call graph around the failing frame.
- **Migrations someone else plans.** `refactor` translates "migrate Pydantic v1 to v2" into Cypher, finds every affected entity, and emits a validated blueprint.
- **Docs that track the code.** `docs` narrates the live graph into a `GUARDIAN_WIKI.md`.
- **The same tools in your editor.** `serve` exposes them over MCP to Cursor, Claude Desktop, or Windsurf.

---

## Quickstart

You need Python 3.11+. Docker only matters if you want Guardian to run Memgraph and Qdrant
for you; point it at your own instances instead if you already run them.

```bash
pip install agentic-dev-guardian          # or: uvx --from agentic-dev-guardian dev-guardian --help

export GUARDIAN_PROVIDER=groq             # groq | anthropic | openai | ollama | local | huggingface
export GUARDIAN_GROQ_API_KEY=...          # groq key; anthropic/openai use ANTHROPIC_API_KEY / OPENAI_API_KEY instead

dev-guardian init                         # starts/health-checks Memgraph + Qdrant, reuses what is up
dev-guardian index /path/to/your/repo     # add --skip-vectors on RAM-constrained machines
dev-guardian evaluate my_feature.diff --repo /path/to/your/repo
```

Extras: `pip install "agentic-dev-guardian[anthropic]"` (also `openai`, `viz`, `tracing`, `all`).

Working from a checkout:

```bash
git clone https://github.com/SmayanKulkarni/Agentic-Dev-Guardian.git
cd Agentic-Dev-Guardian/backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

---

## How It Works

Guardian runs in two stages.

1. **Index.** Tree-sitter parses the codebase. Memgraph stores the structural edges
   (`IMPORTS`, `CALLS`, `INHERITS_FROM`) and Qdrant stores the semantic index.
2. **Act.** LangGraph pipelines query that graph to evaluate PRs, audit risky functions,
   triage incidents, plan refactors, or write architecture docs.

---

## Commands

| CLI Command | What It Does |
|---|---|
| `dev-guardian index <path>` | Parse & ingest a codebase into Memgraph + Qdrant (streaming, memory-safe) |
| `dev-guardian evaluate <diff>` | Run a PR diff through the MoA Gatekeeper + Red Team pipeline |
| `dev-guardian audit <path>` | Find the highest blast-radius functions and red-team them |
| `dev-guardian incident --trace "..."` | Turn a production stack trace into a targeted hotfix blueprint |
| `dev-guardian refactor --pattern "..."` | Build a migration blueprint from a pattern or plain English |
| `dev-guardian docs <path>` | Write a live `GUARDIAN_WIKI.md` from the AST graph |
| `dev-guardian serve` | Start the MCP Server for IDE integration (Cursor, Claude Desktop, Windsurf) |
| `dev-guardian init` | Start and health-check Memgraph + Qdrant; `--print-mcp-config` emits your IDE's JSON block |
| `dev-guardian down` | Stop the containers `init` started, leaving services you run yourself alone |
| `dev-guardian version` | Print the installed version |

---

## Architecture

| Layer | Technology |
|---|---|
| **AST Parsing** | Tree-sitter with a custom Python walker |
| **Knowledge Graph** | Memgraph, holding `ASTNode` relationships (`IMPORTS`, `CALLS`, `INHERITS_FROM`) |
| **Semantic Index** | Qdrant + FastEmbed (ONNX; `--skip-vectors` for RAM-constrained systems) |
| **Hybrid Retrieval** | `HybridRetriever`, fusing Cypher graph results with Qdrant vector search |
| **Agent Orchestration** | LangGraph typed state graphs (`GuardianState`, `SREState`, `RefactorState`) |
| **LLM Engine** | Groq (`llama-3.3-70b-versatile`) by default; also Anthropic, OpenAI, Ollama, or any OpenAI-compatible endpoint |
| **LLMOps & Tracing** | A local SQLite call log always; Langfuse behind the `[tracing]` extra |
| **IDE Integration** | MCP Server over `stdio` or streamable HTTP |

---

## Data Handling

Guardian ships your source code to a third-party LLM provider. Know that before you point
it at anything sensitive.

**What leaves your machine:** the PR diff verbatim, plus the GraphRAG context retrieved
from your indexed codebase (function bodies, structural relations). Both go into the prompt
as-is.

**Where it goes:** to whichever provider `GUARDIAN_PROVIDER` names, so `groq` by default,
or `anthropic` or `openai`. Choosing `ollama` or `local` keeps the calls on your own
infrastructure, though the prompts assume a 70B-class model. Smaller local models lose the
most ground on Red Team test generation, Remediation diffs, and text-to-Cypher.

**What stays local:** the Memgraph AST graph, the Qdrant index, and every deterministic
node, meaning `IncidentTriager`, `RefactorPlanner`, `BlueprintValidator`, and the
supervisor's routing logic. Blast-radius and impact analysis run on your own graph with no
LLM in the loop.

**`--clearance` is not a privacy control.** It scopes how much of the graph a Cypher query
pulls back (`clearance_level <= $cl`). Whatever it does retrieve still reaches the provider,
and the PR diff skips the check.

---

## Agent Pipelines

### PR Evaluation (`evaluate`)
`Gatekeeper → Red Team → Remediation → Decision`

Reads a `.diff` file, pulls GraphRAG context for it, then runs a Mixture-of-Agents pipeline
that lands on `approve`, `remediate`, or `reject`.

### Proactive Audit (`audit`)
`Memgraph (blast-radius query) → Gatekeeper → Red Team → Markdown Report`

Ranks functions by outgoing calls, red-teams the top N without waiting for a PR, and writes
a severity-ranked `guardian_audit.md`.

### Incident Response (`incident`)
`IncidentTriager → SandboxReproducer → HotfixScribe`

Parses a raw stack trace, asks Memgraph for the call graph around the failing function,
tries to reproduce the failure, and drafts a hotfix blueprint.

### Self-Healing Refactor (`refactor`)
`PatternTranslator → RefactorPlanner → MigrationScribe → BlueprintValidator`

Takes a registered pattern such as `migrate-pydantic-v1-to-v2`, or free-form English.
Translates the intent into Cypher, finds every affected entity, and produces a validated
migration blueprint.

### Docs Generation (`docs`)
`StructureExplainer → ADRGenerator → WikiBuilder`

Queries IMPORTS, CALLS, and INHERITS_FROM edges from the live graph, narrates them into
readable section summaries, and assembles a full `GUARDIAN_WIKI.md`.

---

## Providers & Configuration

You choose the provider. Guardian never guesses from whichever key happens to sit in your
environment. `GUARDIAN_PROVIDER` picks the backend and `GUARDIAN_MODEL` overrides that
backend's default model. A missing key for the provider you selected fails the run instead
of falling back to another one.

| Provider | Key | Notes |
|----------|-----|-------|
| `groq` (default) | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| `anthropic` | `ANTHROPIC_API_KEY` | structured output via forced tool-use; needs the `[anthropic]` extra |
| `openai` | `OPENAI_API_KEY` | cloud only; needs the `[openai]` extra |
| `ollama` | none | `http://localhost:11434/v1`, defaults to `qwen3:8b` |
| `local` | none | any OpenAI-compatible engine; set `GUARDIAN_LOCAL_BASE_URL` |
| `huggingface` | `HF_TOKEN` | Inference Providers router |

Running a local or self-hosted model? Set `GUARDIAN_CONTEXT_TOKENS` to that model's real
context size, and `GUARDIAN_TPM` if your endpoint meters you. Guardian cannot infer either
one.

Environment variables win over everything. Dotenv files exist for convenience and load in
ascending priority: `~/.config/guardian/.env`, then `backend/.env`, then `./.env`. Every
setting answers to a `GUARDIAN_`-prefixed name as well as its plain vendor name, and
Guardian writes no configuration of its own.

---

## MCP Integration

`dev-guardian serve` starts a stdio MCP server. It exposes 4 bootstrap tools at startup to
keep your IDE's context window lean:

- `query_guardian_graph` runs semantic and structural search over the indexed codebase
- `list_capabilities` reports what else you can load
- `equip_capability` and `unequip_capability` load and unload a domain's tools on demand

Everything heavier arrives just in time. `equip_capability("pr_governance")` adds
`evaluate_pr_diff`, `codebase_intelligence` adds `impact_analysis`, `index_codebase`,
`audit_codebase` and `generate_architecture_docs`, and `incident_response` and
`self_healing` bring their own. Every CLI command that acts on an indexed repository has
an MCP equivalent — only `init` and `down`, which manage Docker, stay terminal-only, since
nothing auto-starts a container from a session with no terminal to prompt on. The server fires
`notifications/tools/list_changed` on each swap, so a client that caches the tool list for
a session picks the new tools up on its next refresh rather than right away.

Generate the exact block for your install, filled in with your resolved settings:

```bash
dev-guardian init --print-mcp-config                    # Claude Code / Claude Desktop
dev-guardian init --print-mcp-config --client vscode    # .vscode/mcp.json
dev-guardian init --print-mcp-config --client codex     # ~/.codex/config.toml
```

```json
{
  "mcpServers": {
    "guardian": {
      "command": "uvx",
      "args": ["--from", "agentic-dev-guardian", "dev-guardian", "serve"],
      "env": { "GUARDIAN_PROVIDER": "groq", "GUARDIAN_GROQ_API_KEY": "<your-api-key>" }
    }
  }
}
```

`--client` takes `claude`, `cursor`, `windsurf`, `antigravity`, `claude-desktop`, `vscode`,
or `codex`. The shapes are not interchangeable: VS Code keys servers under `servers` and
Codex reads TOML, while the rest use Claude Desktop's `mcpServers`. The printed comment
line names the file to paste into, and goes to stderr so you can redirect the block itself.

Guardian runs its own agent pipeline inside the server process against `GUARDIAN_PROVIDER`,
so `evaluate_pr_diff` behaves the same in every client — it does not borrow the editor's
model and does not need the editor to spawn sub-agents. It does need its own key, or
`GUARDIAN_PROVIDER=ollama` for a fully local run.

Run `dev-guardian init` and index at least one repository before you point an IDE at the
server. `serve` checks the backing services and exits if they are down. Docker is only
needed for that step: nothing auto-starts a container from inside an MCP session, where
there is no terminal to prompt on.

### Clients that ignore `tools/list_changed`

JIT equipping assumes your client refreshes its tool list when the server notifies it. If
yours does not, equipped tools never become visible. Set `GUARDIAN_PRELOAD_CLUSTERS=all` in
the server's `env` block to register every cluster at startup instead — a fuller context
window in exchange for tools that are there from the first message. A comma-separated list
(`pr_governance,codebase_intelligence`) preloads only those.

### Serving over HTTP

Run one Guardian on the machine holding the indexed codebase and connect from elsewhere, or
from several clients, using the streamable-HTTP transport instead of stdio:

```bash
dev-guardian serve --transport streamable-http --port 8000   # endpoint: /mcp
```

It binds to `127.0.0.1` and stays there on purpose. Guardian carries no authentication of
its own and its tools read your indexed codebase, so anything past loopback belongs behind
a reverse proxy that authenticates. Equipped capabilities live in process-global state, so
treat an HTTP server as single-user rather than multi-tenant.

### Optional tracing

Langfuse is an extra, not a dependency. Leave it out and every `@observe` span becomes a
no-op while Guardian runs as usual. The local SQLite call log in `harness/logger.py` keeps
recording either way.

```bash
pip install "agentic-dev-guardian[tracing]"
export LANGFUSE_PUBLIC_KEY=... LANGFUSE_SECRET_KEY=...
```

`GUARDIAN_LANGFUSE_*` / `LANGFUSE_*` in `backend/.env` also work — `core/tracing.py`
copies whatever `GuardianSettings` resolved into `os.environ` (real exported env vars
still win) before Langfuse's own SDK reads it. Langfuse ignores `GuardianSettings`
entirely and reads `os.environ` directly, so without that copy step a `.env`-only
setup silently no-ops every trace with an auth error nobody sees.

---

## Repository Map

```
backend/src/dev_guardian/
├── core/                # Config (Pydantic Settings) + structured logging (structlog)
├── parsers/             # Tree-sitter AST parser + ASTNode/ASTEdge data models
├── graphrag/            # Memgraph client, Qdrant client, vector manager, hybrid retriever
├── agents/              # LangGraph nodes, typed state definitions, graph builders
├── capability_clusters/ # Tool groupings (codebase_intelligence, pr_governance, ...)
├── harness/             # Prompt YAML loading + local SQLite LLM call log
├── prompts/             # Versioned prompt templates
├── skills/              # Agent personas (graphrag_engineer, red_team_tester, ...)
├── docs/                # structure_explainer.py, adr_generator.py, wiki_builder.py
├── cli.py               # Typer CLI entry point (`dev-guardian` command)
└── mcp_server.py        # MCP Server with JIT tool loading for IDE integration
```

The repo also carries `frontend/` (dashboard UI), `evaluation/` (benchmark datasets and
scripts), `infrastructure/` (Memgraph and Qdrant compose files), and `.agents/` (memory,
skills, logs). The PyPI wheel ships none of them. It contains `backend/src/dev_guardian`
and nothing else.

---

## License

MIT. See [LICENSE](https://github.com/SmayanKulkarni/Agentic-Dev-Guardian/blob/main/LICENSE).
