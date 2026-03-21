# Agent Implementation Context: Fusion Project

## Project Goal
Building the `agentic-dev-guardian` Python package—a GraphRAG + MCP server that evaluates proprietary codebases via AST parsing (Tree-sitter) and semantic vectors (Qdrant) to safely govern AI-generated PRs.

## Current Phase: Phase 4 (MCP Server Integration)
**Status**: NOT STARTED
**Objective**: Wrap the engine in Anthropic's Model Context Protocol (MCP) to enable immediate IDE Shift-Left governance.

## Architecture State
- **Event Bus (Kafka)**: Not initialized.
- **GraphRAG (Memgraph + Qdrant)**: ✅ COMPLETE. `MemgraphClient` (`gqlalchemy` Cypher queries) and `QdrantCodeClient` (`fastembed` local CPU vectors). Employs `jinaai/jina-embeddings-v2-base-code` for local embeddings to guarantee proprietary code never leaves the host machine.
- **AST Parser (Tree-sitter)**: ✅ COMPLETE. Purely deterministic, local execution via `tree-sitter-python` (`parsers/ast_parser.py`). No LLM inference is used for parsing nodes/edges.
- **Agent Orchestrator (LangGraph)**: ✅ COMPLETE. MoA + Debate + Remediation StateGraph in `agents/graph.py`. Uses Groq `llama-3.3-70b-versatile` for all LLM inference. Langfuse `@observe()` on every node.
- **MCP Server**: Not initialized. (Phase 4 target)
- **CLI (Typer)**: ✅ COMPLETE. `guardian index`, `guardian evaluate` (live MoA pipeline), `guardian version`.

## Key Interfaces for Phase 4
- `build_guardian_graph()` → returns a compiled LangGraph `StateGraph` ready for `.invoke()`.
- `HybridRetriever.retrieve(query, user_clearance, top_k)` → returns `{"semantic_hits": [...], "graph_context": [...], "merged_context": "..."}`.
- `GuardianSettings` provides `groq_api_key`, `memgraph_host/port`, `qdrant_host/port`, `embedding_model`, `langfuse_*`.

## Phase 3 Agent Architecture (MoA + Self-Healing)
- **Gatekeeper Agent** (`agents/gatekeeper.py`): Architectural violation detector. Uses Groq + GraphRAG context. Langfuse `@observe`.
- **Red Team Tester** (`agents/red_team.py`): Adversarial PyTest generator. Groq temp=0.3 for creative exploits. Langfuse `@observe`.
- **Supervisor** (`agents/graph.py:supervisor_node`): Merges MoA reports. Routes: both pass→approve, both fail→remediate, disagree→debate.
- **Debate Node** (`agents/graph.py:debate_node`): Resolves contradictions using GraphRAG as ground truth. Groq temp=0.0.
- **Remediation Specialist** (`agents/remediation.py`): Self-Healer that generates corrected code diffs using failed test traces + GraphRAG connected-components context.
- **State Schema** (`agents/state.py`): `GuardianState` TypedDict with `Annotated[list, operator.add]` for append-only message logs.

## Next Immediate Execution Steps
1. Create `mcp_server.py` using the official `mcp` Python SDK (FastMCP/stdio).
2. Expose `@mcp.tool()` for `query_guardian_graph()` and `evaluate_local_diff()`.
3. Expose `@mcp.resource()` for dynamic security guidelines injection.

## Hardware & Environment Constraints
- **LLM Provider**: **Groq**. All AI inference MUST run on Groq. Model: `llama-3.3-70b-versatile`.
- **Secrets Management**: All API keys MUST be in `backend/.env`.
- **Embedding Model**: `jinaai/jina-embeddings-v2-base-code` via `fastembed` (local CPU, never external API).
