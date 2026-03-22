# Human-in-the-Loop Documentation

This document is strictly maintained for the Human engineering supervisor. Whenever an AI Coding Agent finishes a runtime execution phase, they MUST translate their highly technical, exhaustive code changes into a clear, macroscopic summary below. 

The goal of this file is to help the Human understand *exactly* what coding has been completed from the ground up, what changes were made, and how they affect the codebase without needing to read raw pull request diffs.

## Current Project State
- **Current Phase:** Phase 3 COMPLETE ✅. Phase 4 (MCP Server Integration) is next.
- **Codebase Impact:** The `dev-guardian` system can now parse code, store it in two databases, AND autonomously evaluate PRs using a multi-agent AI pipeline that can fix its own rejected code.

---

### Phase 1 Summary: Core Python Package & AST Parser Engine

**What was built:**
We created a complete, installable Python package called `agentic-dev-guardian` inside the `backend/` folder. It is a command-line tool that a developer can run from their terminal.

**What can it do right now:**
- You can type `guardian index /path/to/any/python/project` in the terminal, and it will mathematically scan every single Python file, identify all functions, classes, methods, and variables, and map out exactly how they are connected.
- It successfully parsed its own source code and found **23 structural entities** and **112 relationships**.

**Why this matters:**
This is the foundational layer. Before the AI agents can evaluate a Pull Request, they need to *understand* the codebase structure. This parser builds that understanding without ever sending code to an external AI — purely local mathematical analysis (Data Minimization Security Guardrail).

---

### Phase 2 Summary: Memgraph & Qdrant Database Integration

**What was built:**
We created the "brain storage" layer — the databases that hold the parsed knowledge graph. Think of these like two complementary filing cabinets:
1. **Memgraph (Graph Database)**: Stores the *exact structural connections* extracted by **Tree-sitter** (`tree-sitter-python`). It creates edges like "Function A CALLS Function B" and is queried using Cypher (`gqlalchemy`). This answers precise questions like "What will break if I delete this function?"
2. **Qdrant (Vector Database)**: Stores *semantic meaning* of code entities using AI embeddings. We strictly use **FastEmbed** running the `jinaai/jina-embeddings-v2-base-code` model *locally on CPU*. This ensures our Data Minimization Guardrail is upheld: your raw code is never sent to OpenAI or Groq to be vectorized.

**What can it do right now:**
- The `HybridRetriever` class can ingest all the parsed AST data into both databases at once.
- It can then execute a "dual-brain" query: ask Qdrant for semantically similar code entities, then expand each hit through Memgraph's structural graph to find all connected dependencies.
- The combined result is formatted into a clean text block ready to be injected into an LLM prompt.

**Critical Security Feature:**
Every single database query (both Memgraph AND Qdrant) enforces **ABAC (Attribute-Based Access Control)** filters. This means if a junior developer with clearance level 1 queries the system, they will NEVER see code entities marked as clearance level 2 or higher.

---

### Phase 3 Summary: LangGraph Multi-Agent AI Pipeline (MoA + Self-Healing)

**What was built:**
This is the "AI brain" itself — the multi-agent pipeline that actually evaluates Pull Requests and either approves them, rejects them, or **fixes them automatically**. We implemented a cutting-edge **Mixture-of-Agents (MoA)** architecture with a **Debate Resolution** mechanism and a **Self-Healing Remediation** agent.

**How the pipeline works (step by step):**
1. **You run:** `guardian evaluate my_pr.diff --repo /path/to/codebase --clearance 2`
2. **GraphRAG Context Retrieval:** The system queries both Memgraph and Qdrant to understand how the existing codebase is structured and what the PR's code changes might affect.
3. **MoA Layer (Two agents run concurrently):**
   - **Gatekeeper Agent** — Reviews the PR diff + GraphRAG context for architectural violations (broken imports, removed functions still called elsewhere, dependency regressions).
   - **Red Team Tester Agent** — Tries to *break* the PR code by writing hostile PyTest edge-cases (null inputs, type mismatches, boundary values, missing error handlers).
4. **Supervisor Node** — Collects both reports and makes a routing decision:
   - Both PASS → ✅ Approve the PR.
   - Both FAIL → Route to Remediation (skip debate, go fix).
   - They disagree → Route to the Debate Node.
5. **Debate Node** (if needed) — Uses the GraphRAG context as mathematical ground truth to determine which agent is correct, resolving the contradiction with zero hallucination.
6. **Remediation Specialist (The Self-Healer)** — If the PR is rejected, this agent reads ALL evidence: the failing Red Team tests, the Gatekeeper violations, and the full GraphRAG connected-component context. It then generates a complete, drop-in replacement code fix.

**What makes this novel:**
- Traditional code review tools just say "this is wrong." Our system says "this is wrong, here's exactly why based on your codebase graph, and here's the corrected code."
- The Debate mechanism prevents the common multi-agent hallucination problem where agents reinforce each other's mistakes.

**All AI inference runs on Groq** (`llama-3.3-70b-versatile`) for ultra-low latency. Every agent node has **Langfuse `@observe()` instrumentation** for full token usage tracking and output auditing.

**What's NOT built yet:**
- The MCP Server for IDE integration — that's Phase 4.

---

### 2026-03-22 Update: Logic & Correctness Hardening

**What changed (simple view):**
We performed a focused reliability pass to remove hidden correctness bugs that could quietly degrade the system over time.

**What was fixed:**
1. **Duplicate vector prevention**
- Before: re-indexing could create duplicate semantic vectors.
- Now: vector IDs are deterministic, so re-indexing updates existing entries consistently.

2. **Graph edge safety across files**
- Before: similarly named symbols in different files could be linked incorrectly.
- Now: edge insertion resolves targets with file-aware identity, reducing cross-file symbol collisions.

3. **Cleaner impact analysis**
- Before: impact analysis traversed every relationship type and produced noisy false positives.
- Now: impact analysis follows CALLS paths only, which better represents execution impact.

4. **Safer decision routing**
- Before: WARN+FAIL outcomes could route to debate unexpectedly.
- Now: WARN+FAIL routes directly to remediation, which is the safer policy.

5. **Parser correctness improvements**
- Enforced explicit python-only support (instead of silently accepting unsupported language values).
- Improved import parsing for statements like `import a, b as c` and `from x import y`.
- Corrected parsed-file counting so failed file reads are not counted as successful parses.

6. **Output parsing robustness**
- Remediation code extraction now handles a wider variety of markdown code-fence language tags.

7. **Code clarity cleanup**
- Removed redundant details-parsing branches in Gatekeeper and Red Team report parsers.
- Updated CLI docstrings so behavior descriptions match what commands actually do.

**Impact for the project:**
- Improves trust in indexing results and retrieval quality.
- Reduces false alarms in architectural impact checks.
- Makes remediation routing behavior more predictable and policy-consistent.
- Lowers long-run data drift risk in the vector store.

**Project phase status:**
- Phase 3 remains complete.
- Phase 4 MCP Server Integration is **COMPLETE** ✅.
- **Phase 5 (Project Expansion)** has been formally brainstormed and documented.

---

### Phase 4 Summary: MCP Server Integration (Model Context Protocol)

**What was built:**
The Guardian's internal GraphRAG engine and LangGraph MoA pipeline are now exposed to external IDE assistants (Cursor, Claude Desktop, Windsurf) via the Anthropic Model Context Protocol.

**New files created:**
- `mcp_server.py` — The MCP server entry point using `FastMCP` with `stdio` transport.

**What it exposes:**
- **4 MCP Tools**: `query_guardian_graph`, `evaluate_pr_diff`, `impact_analysis`, `index_codebase`
- **2 MCP Resources**: `guardian://status` (system health), `guardian://security-policy` (ABAC rules)
- **2 MCP Prompts**: `review_pr` (structured PR review), `investigate_function` (deep-dive analysis)

**How to use it:**
- Run `guardian serve` from the terminal to start the MCP stdio server.
- Configure your IDE's MCP settings to point to the `guardian serve` command.
- The IDE agent can then natively invoke Guardian tools during coding sessions.

**What was changed in existing files:**
- `pyproject.toml` — Added `mcp[cli]>=1.0.0` dependency.
- `cli.py` — Added the `guardian serve` command.

