# Human-in-the-Loop Documentation

This document is strictly maintained for the Human engineering supervisor. Whenever an AI Coding Agent finishes a runtime execution phase, they MUST translate their highly technical, exhaustive code changes into a clear, macroscopic summary below. 

The goal of this file is to help the Human understand *exactly* what coding has been completed from the ground up, what changes were made, and how they affect the codebase without needing to read raw pull request diffs.

## Current Project State
- **Current Phase:** Phase 2 COMPLETE ✅. Phase 3 (LangGraph Agent Workflows) is next.
- **Codebase Impact:** The `dev-guardian` system can now parse code AND store it in two databases simultaneously.

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
Every single database query (both Memgraph AND Qdrant) enforces **ABAC (Attribute-Based Access Control)** filters. This means if a junior developer with clearance level 1 queries the system, they will NEVER see code entities marked as clearance level 2 or higher. The filter is hardcoded into every Cypher and vector query — it cannot be bypassed.

**What's NOT built yet:**
- The AI agents that *use* this retrieved context to evaluate PRs — that's Phase 3 (LangGraph).
- The MCP Server for IDE integration — that's Phase 4.
