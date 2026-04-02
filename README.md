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
| `guardian index <path>` | Parse & ingest a codebase into Memgraph + Qdrant (streaming, memory-safe) |
| `guardian evaluate <diff>` | Run a PR diff through the MoA Gatekeeper + Red Team pipeline |
| `guardian audit <path>` | Find the highest blast-radius functions and red-team them proactively |
| `guardian incident --trace "..."` | Triage a production stack trace → generate a targeted hotfix blueprint |
| `guardian refactor --pattern "..."` | Generate a self-healing migration blueprint from a pattern or natural language |
| `guardian docs <path>` | Generate a live `GUARDIAN_WIKI.md` from the AST graph via Groq |
| `guardian serve` | Launch the MCP Server for IDE integration (Cursor, Claude Desktop, Windsurf) |

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
| **LLMOps & Tracing** | Langfuse for token observability and quality gating |
| **IDE Integration** | MCP Server (`stdio` transport) — exposes Guardian tools to any MCP-compatible IDE |

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

**Prerequisites:** Python 3.11+, a running Memgraph instance, and a Qdrant instance.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in GROQ_API_KEY, Memgraph, Qdrant, Langfuse credentials
```

**Index a codebase:**
```bash
guardian index /path/to/your/repo
# Memory-constrained? Skip Qdrant ONNX embeddings:
guardian index /path/to/your/repo --skip-vectors
```

**Evaluate a PR:**
```bash
guardian evaluate my_feature.diff --repo /path/to/your/repo
```

**Run the MCP Server (for Cursor / Claude Desktop):**
```bash
guardian serve
```

---

## 🔌 MCP Integration

The `guardian serve` command starts a stdio MCP server that exposes 4 tools to your IDE:

- `query_guardian_graph` — semantic + structural search of the indexed codebase
- `evaluate_pr_diff` — run the full MoA evaluation pipeline on a diff
- `impact_analysis` — find all callers/dependents of a given function
- `index_codebase` — trigger a fresh index from within the IDE
