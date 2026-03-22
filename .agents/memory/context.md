# Agent Implementation Context: Fusion Project

## Project Goal
Building the `agentic-dev-guardian` Python package—a GraphRAG + MCP server that evaluates proprietary codebases via AST parsing (Tree-sitter) and semantic vectors (Qdrant) to safely govern AI-generated PRs.

## Current Phase: Phase 5 (Advanced Guardian Capabilities)
**Status**: Phase 4 COMPLETE ✅. Phase 5 expansion is next.
**Objective**: Extend the Guardian into a multi-domain autonomous engineering lifecycle manager.

## Architecture State
- **Event Bus (Kafka)**: Not initialized.
- **GraphRAG (Memgraph + Qdrant)**: ✅ COMPLETE. `MemgraphClient` (`gqlalchemy` Cypher queries) and `QdrantCodeClient` (`fastembed` local CPU vectors). Employs `jinaai/jina-embeddings-v2-base-code` for local embeddings to guarantee proprietary code never leaves the host machine.
- **AST Parser (Tree-sitter)**: ✅ COMPLETE. Purely deterministic, local execution via `tree-sitter-python` (`parsers/ast_parser.py`). No LLM inference is used for parsing nodes/edges.
- **Agent Orchestrator (LangGraph)**: ✅ COMPLETE. MoA + Debate + Remediation StateGraph in `agents/graph.py`. Uses Groq `llama-3.3-70b-versatile` for all LLM inference. Langfuse `@observe()` on every node.
- **MCP Server**: ✅ COMPLETE. `mcp_server.py` using `FastMCP` (stdio transport). Exposes 4 tools, 2 resources, 2 prompts. CLI entry point: `guardian serve`.
- **CLI (Typer)**: ✅ COMPLETE. `guardian index`, `guardian evaluate` (live MoA pipeline), `guardian version`.

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

## Next Immediate Execution Steps
1. Implement Phase 5.1: Self-Healing Codebase Maintenance.
2. Implement Phase 5.2: Automated Incident Response (SRE Sandbox).
3. Implement Phase 5.3: Auto-Generating Dynamic Documentation.
4. Implement Phase 5.4: Live PII & Taint-Tracking Auditor.
5. Implement Phase 5.5: Cloud Cost & FinOps Optimization.
6. Implement Phase 5.6: Autonomous Developer Onboarding Engine.

## Hardware & Environment Constraints
- **LLM Provider**: **Groq**. All AI inference MUST run on Groq. Model: `llama-3.3-70b-versatile`.
- **Secrets Management**: All API keys MUST be in `backend/.env`.
- **Embedding Model**: `jinaai/jina-embeddings-v2-base-code` via `fastembed` (local CPU, never external API).

## Latest Stabilization Update (2026-03-22)
- Completed a logic/correctness hardening pass across parser, GraphRAG clients, and orchestration routing.
- Resolved non-deterministic Qdrant point IDs to enforce stable upsert behavior across re-indexing runs.
- Reduced graph edge mis-linking risk by strengthening target path resolution during Memgraph edge upserts.
- Restricted impact analysis traversal to CALLS edges for lower false-positive blast radius.
- Corrected supervisor handling for WARN+FAIL outcomes to route directly to remediation.
- Hardened remediation code-fence parsing and cleaned redundant report parser branches.
- Aligned CLI docstrings with command side effects.

## Operational Note
- A dedicated audit/fix artifact was written to `.agents/logs/logic_correctness_audit_2026-03-22.md`.

## Current Phase
- Phase 4 is **COMPLETE** ✅ (`mcp_server.py` with 4 tools, 2 resources, 2 prompts, `guardian serve` CLI).
- Phase 5 Project Expansion is the next implementation target.
