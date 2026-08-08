# Agentic Dev Guardian 🛡️

> A GraphRAG-powered multi-agent system that deeply understands your codebase and autonomously guards it — generating architectural docs, gatekeeping pull requests, red-teaming code, and self-healing technical debt.

---

## How It Works

The Guardian works in two stages:

1. **Index** — Parse a codebase with Tree-sitter and build a live knowledge graph in Memgraph (structural edges: `IMPORTS`, `CALLS`, `INHERITS_FROM`) and a semantic index in Qdrant.
2. **Act** — Run LangGraph-powered agent pipelines that query this graph to make intelligent decisions: evaluate PRs, audit risky functions, triage incidents, generate refactoring blueprints, or produce live architecture docs.

---

## 🧠 What the Agents Can Do

| CLI Command | What It Does |
|---|---|
| `dev-guardian index <path>` | Parse & ingest a codebase into Memgraph + Qdrant (streaming, memory-safe) |
| `dev-guardian evaluate <diff>` | Run a PR diff through the MoA Gatekeeper + Red Team pipeline |
| `dev-guardian audit <path>` | Find the highest blast-radius functions and red-team them proactively |
| `dev-guardian incident --trace "..."` | Triage a production stack trace → generate a targeted hotfix blueprint |
| `dev-guardian refactor --pattern "..."` | Generate a self-healing migration blueprint from a pattern or natural language |
| `dev-guardian docs <path>` | Generate a live `GUARDIAN_WIKI.md` from the AST graph via Groq |
| `dev-guardian serve` | Launch the MCP Server for IDE integration (Cursor, Claude Desktop, Windsurf) |
| `dev-guardian init` | Start and health-check Memgraph + Qdrant; `--print-mcp-config` emits your IDE's JSON block |
| `dev-guardian down` | Stop the containers `init` started (never touches services you run yourself) |

---

## 🏗️ Architecture

| Layer | Technology |
|---|---|
| **AST Parsing** | Tree-sitter + custom Python walker |
| **Knowledge Graph** | Memgraph — stores `ASTNode` relationships (`IMPORTS`, `CALLS`, `INHERITS_FROM`) |
| **Semantic Index** | Qdrant + FastEmbed (ONNX, `--skip-vectors` for RAM-constrained systems) |
| **Hybrid Retrieval** | `HybridRetriever` — fuses Cypher graph results + Qdrant vector search |
| **Agent Orchestration** | LangGraph typed state graphs (`GuardianState`, `SREState`, `RefactorState`) |
| **LLM Engine** | Groq (`llama-3.3-70b-versatile`) for reasoning, code generation, and narration |
| **LLMOps & Tracing** | Local SQLite call log always; Langfuse optionally (`[tracing]` extra) |
| **IDE Integration** | MCP Server (`stdio` transport) — exposes Guardian tools to any MCP-compatible IDE |

---

## 📤 Data Handling

Guardian sends your source code to a third-party LLM provider. Be clear about this before pointing it at anything sensitive.

**What leaves your machine:** the PR diff verbatim, and the GraphRAG context retrieved from your indexed codebase (function bodies, structural relations). Both go into the prompt as-is.

**Where it goes:** whichever provider `GUARDIAN_PROVIDER` selects — `groq` (default), `anthropic`, or `openai`. Setting it to `ollama` or `local` keeps calls on your own infrastructure, but note that the prompts are tuned for a 70B-class model and quality drops on small local models, most visibly on Red Team test generation, Remediation diffs, and text-to-Cypher.

**What stays local:** the Memgraph AST graph, the Qdrant index, and every deterministic node — `IncidentTriager`, `RefactorPlanner`, `BlueprintValidator`, and the supervisor's routing logic. Blast-radius and impact analysis run entirely on your own graph with no LLM involved.

**`--clearance` is not a privacy control.** It scopes how much of the graph a Cypher query pulls back (`clearance_level <= $cl`). Anything it does retrieve is still sent to the provider, and the PR diff bypasses it entirely.

---

## 🤖 Agent Pipelines

### PR Evaluation (`evaluate`)
`Gatekeeper → Red Team → Remediation → Decision`

Evaluates a `.diff` file by first querying GraphRAG context, then passing through a Mixture-of-Agents (MoA) pipeline that produces a final `approve / remediate / reject` verdict.

### Proactive Audit (`audit`)
`Memgraph (blast-radius query) → Gatekeeper → Red Team → Markdown Report`

Finds the N functions with the most outgoing calls (highest blast radius) and red-teams them without needing a PR, writing a severity-ranked `guardian_audit.md`.

### Incident Response (`incident`)
`IncidentTriager → SandboxReproducer → HotfixScribe`

Parses a raw stack trace, queries Memgraph for the call graph surrounding the failing function, attempts to reproduce the failure, and generates a detailed hotfix blueprint.

### Self-Healing Refactor (`refactor`)
`PatternTranslator → RefactorPlanner → MigrationScribe → BlueprintValidator`

Accepts registered patterns (e.g. `migrate-pydantic-v1-to-v2`) or free-form English. Translates intent into a Cypher query, finds all affected entities, and produces a validated migration blueprint.

### Docs Generation (`docs`)
`StructureExplainer → ADRGenerator → WikiBuilder`

Queries IMPORTS, CALLS, and INHERITS_FROM edges from the live Memgraph graph and uses Groq to narrate them into human-readable section summaries, then assembles a full `GUARDIAN_WIKI.md`.

---

## 🗂️ Repository Map

```
backend/src/dev_guardian/
├── core/               # Config (Pydantic Settings) + structured logging (structlog)
├── parsers/            # Tree-sitter AST parser + ASTNode/ASTEdge data models
├── graphrag/           # Memgraph client, Qdrant client, vector manager, hybrid retriever
├── agents/             # All LangGraph nodes + typed state definitions + graph builders
├── capability_clusters/ # High-level tool groupings (codebase_intelligence, pr_governance, etc.)
├── docs/               # structure_explainer.py, adr_generator.py, wiki_builder.py
├── cli.py              # Typer CLI entry point (`guardian` command)
└── mcp_server.py       # MCP Server with JIT tool loading for IDE integration

.agents/
├── memory/             # Architecture blueprint, context, package capabilities
├── skills/             # Specialized agent personas (graphrag_engineer, red_team_tester, etc.)
└── logs/               # Implementation logs and audit records
```

---

## ⚙️ Getting Started

**Prerequisites:** Python 3.11+, and Docker (only if you want Guardian to run Memgraph and
Qdrant for you — point it at your own instances instead if you prefer).

```bash
pip install agentic-dev-guardian      # or: uvx --from agentic-dev-guardian dev-guardian --help

export GUARDIAN_PROVIDER=groq         # groq | anthropic | openai | ollama | local | huggingface
export GUARDIAN_GROQ_API_KEY=...      # the key for whichever provider you picked

dev-guardian init                     # starts/health-checks Memgraph + Qdrant, reuses what is up
```

From a checkout instead:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

**Index a codebase:**
```bash
dev-guardian index /path/to/your/repo
# Memory-constrained? Skip Qdrant ONNX embeddings:
dev-guardian index /path/to/your/repo --skip-vectors
```

**Evaluate a PR:**
```bash
dev-guardian evaluate my_feature.diff --repo /path/to/your/repo
```

**Run the MCP Server (for Cursor / Claude Desktop):**
```bash
dev-guardian serve
```

### Providers

Selection is explicit — Guardian never guesses from whichever key happens to be in your
environment. `GUARDIAN_PROVIDER` picks the backend, `GUARDIAN_MODEL` overrides that
backend's default model, and a missing key for the selected provider is a hard failure
rather than a silent fallback.

| Provider | Key | Notes |
|----------|-----|-------|
| `groq` (default) | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| `anthropic` | `ANTHROPIC_API_KEY` | structured output via forced tool-use |
| `openai` | `OPENAI_API_KEY` | cloud only |
| `ollama` | — | `http://localhost:11434/v1`, defaults to `qwen3:8b` |
| `local` | — | any OpenAI-compatible engine; set `GUARDIAN_LOCAL_BASE_URL` |
| `huggingface` | `HF_TOKEN` | Inference Providers router |

For a local or self-hosted model, set `GUARDIAN_CONTEXT_TOKENS` to that model's real context
size (and `GUARDIAN_TPM` if your endpoint is metered) — Guardian cannot infer either.

### Configuration

Environment variables win over everything; dotenv files are convenience only, read in
ascending priority: `~/.config/guardian/.env`, then `backend/.env`, then `./.env`. Every
setting takes a `GUARDIAN_`-prefixed name as well as its plain vendor name. Guardian writes
no configuration of its own.

---

## 🔌 MCP Integration

The `dev-guardian serve` command starts a stdio MCP server. To keep your IDE's context
window lean it exposes only 4 bootstrap tools at startup:

- `query_guardian_graph` — semantic + structural search of the indexed codebase
- `list_capabilities` — what else can be loaded
- `equip_capability` / `unequip_capability` — load and unload a domain's tools on demand

Everything heavier arrives just-in-time. `equip_capability("pr_governance")` adds
`evaluate_pr_diff`; `codebase_intelligence` adds `impact_analysis` and `index_codebase`;
`incident_response` and `self_healing` add their own. The server fires
`notifications/tools/list_changed` on each change — clients that cache the tool list for a
session pick the new tools up on their next refresh rather than immediately.

Generate the exact block for your install — it fills in your resolved settings:

```bash
dev-guardian init --print-mcp-config
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

Run `dev-guardian init` and index at least one repository before pointing your IDE at the
server; `serve` verifies the backing services and exits if they are down.

### Serving over HTTP

To run one Guardian on the machine that holds the indexed codebase and connect to it from
elsewhere (or from several clients), use the streamable-HTTP transport instead of stdio:

```bash
dev-guardian serve --transport streamable-http --port 8000   # endpoint: /mcp
```

It binds to `127.0.0.1` by default and deliberately stays there: Guardian has no
authentication of its own and its tools read your indexed codebase, so exposing it beyond
loopback belongs behind a reverse proxy that authenticates. Equipped capabilities are
process-global, so treat an HTTP server as single-user, not multi-tenant.

### Optional tracing

Langfuse is an extra, not a dependency. Without it every `@observe` span is a no-op and
Guardian runs normally; the local SQLite call log in `harness/logger.py` is unaffected.

```bash
pip install "agentic-dev-guardian[tracing]"
export LANGFUSE_PUBLIC_KEY=... LANGFUSE_SECRET_KEY=...
```
