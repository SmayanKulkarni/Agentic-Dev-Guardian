# Agentic Dev Guardian — Launch Guide

## One-liner
A GraphRAG-powered MCP server that indexes your codebase into a knowledge graph, then gives your IDE agent tools to gate PRs by blast radius, red-team risky functions, triage incidents from a stack trace, plan migrations, and write architecture docs that track the live code.

## Category
Code Review / Static Analysis / Developer Productivity

## Tags
graphrag, code-review, static-analysis, pr-review, red-team, knowledge-graph, langgraph, kuzu, qdrant, incident-response, refactoring, documentation

## Why it's different
Most code-review agents only see the diff. Guardian parses the repo with Tree-sitter into a call/import/inheritance graph in an embedded Kùzu database, plus a Qdrant semantic index, so a PR verdict is grounded in what the code actually calls and is called by — not just what fits in the context window.

## Install

```bash
pip install agentic-dev-guardian
# or run without installing:
uvx --from agentic-dev-guardian dev-guardian --help
```

Requires Python 3.11+. Nothing else — the graph and vector stores are embedded and run inside the Guardian process.

## MCP config

```bash
dev-guardian mcp-config                    # Claude Code / Claude Desktop
dev-guardian mcp-config --client vscode
dev-guardian mcp-config --client codex
dev-guardian mcp-config --client cursor
dev-guardian mcp-config --client windsurf
```

Example (stdio, Claude Desktop shape):

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

Before pointing an IDE at it: `dev-guardian index /path/to/repo` at least once.

## Tools exposed

Starts lean — 4 bootstrap tools — and loads the rest just-in-time so the IDE's context window stays small:

- `query_guardian_graph` — semantic + structural search over the indexed codebase
- `list_capabilities` / `equip_capability` / `unequip_capability` — load/unload tool groups on demand

Equippable clusters: `pr_governance` (`evaluate_pr_diff`), `codebase_intelligence` (`impact_analysis`, `index_codebase`, `audit_codebase`, `generate_architecture_docs`), `incident_response`, `self_healing`.

Clients that don't refresh their tool list on `notifications/tools/list_changed` can set `GUARDIAN_PRELOAD_CLUSTERS=all` to register everything at startup instead.

## Required setup

Pick one LLM provider — Guardian never guesses from an ambient key:

| Provider | Key |
|---|---|
| `groq` (default) | `GROQ_API_KEY` |
| `anthropic` | `ANTHROPIC_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `ollama` / `local` | none — self-hosted |
| `huggingface` | `HF_TOKEN` |

## Data handling note
Guardian sends the PR diff and retrieved graph context (function bodies, structural relations) to whichever provider `GUARDIAN_PROVIDER` names. Choosing `ollama` or `local` keeps everything on your own infrastructure. Full detail in the [README's Data Handling section](https://github.com/SmayanKulkarni/Agentic-Dev-Guardian#data-handling).

## Links
- Source: https://github.com/SmayanKulkarni/Agentic-Dev-Guardian
- PyPI: https://pypi.org/project/agentic-dev-guardian/
- Issues: https://github.com/SmayanKulkarni/Agentic-Dev-Guardian/issues
- License: MIT
