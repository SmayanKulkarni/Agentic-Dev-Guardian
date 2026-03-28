# Agent Implementation Context: Fusion Project

## Project Goal
Building the `agentic-dev-guardian` Python package—a GraphRAG + MCP server that evaluates proprietary codebases via AST parsing (Tree-sitter) and semantic vectors (Qdrant) to safely govern AI-generated PRs.

## Current Phase: Phase 5 (Advanced Guardian Capabilities)
**Status**: Phases 5.1, 5.2 COMPLETE ✅. Phase 5.7 (Adaptive JIT Embeddings) COMPLETE ✅. Phase 5.3 (Documentation) is next.
**Objective**: Extend the Guardian into a multi-domain autonomous engineering lifecycle manager.

## Architecture State
- **Event Bus (Kafka)**: Not initialized.
- **GraphRAG (Memgraph + Qdrant)**: ✅ COMPLETE. `MemgraphClient` (`gqlalchemy` Cypher queries) and `QdrantCodeClient` (`fastembed` local CPU vectors). Employs `jinaai/jina-embeddings-v2-base-code` for local embeddings to guarantee proprietary code never leaves the host machine.
- **AST Parser (Tree-sitter)**: ✅ COMPLETE. Purely deterministic, local execution via `tree-sitter-python` (`parsers/ast_parser.py`). No LLM inference is used for parsing nodes/edges.
- **Agent Orchestrator (LangGraph)**: ✅ COMPLETE. MoA + Debate + Remediation StateGraph in `agents/graph.py`. Uses Groq `llama-3.3-70b-versatile` for all LLM inference. Langfuse `@observe()` on every node.
- **MCP Server**: ✅ COMPLETE. `mcp_server.py` using `FastMCP` (stdio transport). Exposes 4 tools, 2 resources, 2 prompts. CLI entry point: `guardian serve`.
- **CLI (Typer)**: ✅ COMPLETE. `guardian index` (with `--skip-vectors` + adaptive JIT auto-detection), `guardian evaluate` (MoA + JIT embeddings), `guardian audit` (proactive blast-radius scanning), `guardian incident` (SRE triage), `guardian refactor` (self-healing refactoring + text-to-Cypher), `guardian query` (NL → Cypher), `guardian serve`, `guardian version`.
- **Adaptive JIT Vector Embeddings**: ✅ COMPLETE. `vector_manager.predict_embedding_strategy()` auto-detects large repos (≥300 files). `HybridRetriever.jit_embed_nodes()` embeds only the queried subgraph at runtime, preventing OOM on repos like `sktime` (1,550 files).

## Key Interfaces for Phase 5
- `build_guardian_graph()` → returns a compiled LangGraph `StateGraph` ready for `.invoke()`.
- `HybridRetriever.retrieve(query, user_clearance, top_k)` → returns `{"semantic_hits": [...], "graph_context": [...], "merged_context": "..."}`.
- `GuardianSettings` provides `groq_api_key`, `memgraph_host/port`, `qdrant_host/port`, `embedding_model`, `langfuse_*`.
- `run_server()` → starts MCP stdio loop exposing all tools/resources/prompts.

## Phase 3 Agent Architecture (MoA + Self-Healing)
- **Gatekeeper Agent** (`agents/gatekeeper.py`): Architectural violation detector. Uses Groq + GraphRAG context. Langfuse `@observe`.
- **Red Team Tester** (`agents/red_team.py`): Adversarial PyTest generator. Groq temp=0.3 for creative exploits. Langfuse `@observe`.
- **Supervisor** (`agents/graph.py:supervisor_node`): Merges MoA reports. Routes: both pass→approve, both fail→remediate, disagree→debate.
- **Debate Node** (`agents/graph.py:debate_node`): Resolves contradictions using GraphRAG as ground truth. Groq temp=0.0.
- **Remediation Specialist** (`agents/remediation.py`): Self-Healer that generates corrected code diffs using failed test traces + GraphRAG connected-components context.
- **State Schema** (`agents/state.py`): `GuardianState` TypedDict with `Annotated[list, operator.add]` for append-only message logs.

## Phase 5 Completion Status
- [x] Phase 5.1: Self-Healing Codebase Maintenance (`guardian refactor` + text-to-Cypher)
- [x] Phase 5.2: Automated Incident Response (`guardian incident`, `incident_triager.py`, `sre_graph.py`)
- [ ] Phase 5.3: Auto-Generating Dynamic Documentation (Memgraph-driven ADRs & Mermaid diagrams) ← NEXT
- [ ] Phase 5.4: Live PII & Taint-Tracking Auditor
- [ ] Phase 5.5: Cloud Cost & FinOps Optimization Architect
- [ ] Phase 5.6: Autonomous Developer Onboarding Engine
- [x] Phase 5.7: Adaptive JIT Vector Embeddings (OOM-safe, 100% local)

## Hardware & Environment Constraints
- **LLM Provider**: **Groq**. All AI inference MUST run on Groq. Model: `llama-3.3-70b-versatile`.
- **Secrets Management**: All API keys MUST be in `backend/.env`.
- **Embedding Model**: `jinaai/jina-embeddings-v2-base-code` via `fastembed` (local CPU, never external API).

## Latest Updates (2026-03-27)

### OOM Mitigation
- `guardian index` now streams file-by-file with `gc.collect()` after each file.
- `--skip-vectors` flag skips ONNX model loading (~270MB RAM saving).
- Tested on `sktime` (1,550 files): 10,038 nodes, 66,472 edges ingested without crash.

### Adaptive JIT Vector Embeddings (Phase 5.7)
- `graphrag/vector_manager.py`: `predict_embedding_strategy()` counts files and returns `"global"` or `"lazy"`.
- `guardian index` auto-switches to `--skip-vectors` for repos ≥ 300 files.
- `HybridRetriever.jit_embed_nodes()`: Embeds only queried graph nodes at runtime.
- All pipelines (`evaluate`, `audit`) now emit real vector context instead of empty strings.

### Known Limitations
- Groq TPM limit (12k tokens/min): Large diffs or large GraphRAG contexts may hit 413 errors. Use `--top 3` for audits.
- `guardian refactor` for aliased imports (e.g. `from x import Foo as _Bar`) returns 0 matches — Tree-sitter AST does not resolve aliases.
- Global semantic search (no starting node) is unavailable on lazy-indexed repos; all queries must start from a graph node.
