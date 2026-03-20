# Agent Implementation Context: Fusion Project

## Project Goal
Building the `agentic-dev-guardian` Python package—a GraphRAG + MCP server that evaluates proprietary codebases via AST parsing (Tree-sitter) and semantic vectors (Qdrant) to safely govern AI-generated PRs.

## Current Phase: Phase 3 (LangGraph Agent Workflows)
**Status**: NOT STARTED
**Objective**: Instantiate the multi-agent cyclic reasoning orchestration using LangGraph with TypedDict state management.

## Architecture State
- **Event Bus (Kafka)**: Not initialized.
- **GraphRAG (Memgraph + Qdrant)**: ✅ COMPLETE. `MemgraphClient` (`gqlalchemy` Cypher queries) and `QdrantCodeClient` (`fastembed` local CPU vectors). Employs `jinaai/jina-embeddings-v2-base-code` for local embeddings to guarantee proprietary code never leaves the host machine.
- **AST Parser (Tree-sitter)**: ✅ COMPLETE. Purely deterministic, local execution via `tree-sitter-python` (`parsers/ast_parser.py`). No LLM inference is used for parsing nodes/edges.
- **Agent Orchestrator (LangGraph)**: Not initialized. (Phase 3 target)
- **MCP Server**: Not initialized.
- **CLI (Typer)**: ✅ COMPLETE. `guardian index`, `guardian evaluate`, `guardian version`.

## Key Interfaces for Phase 3
- `HybridRetriever.retrieve(query, user_clearance, top_k)` → returns `{"semantic_hits": [...], "graph_context": [...], "merged_context": "..."}`.
- `ASTParser.parse_directory(path)` → returns `ParseResult(nodes=[], edges=[])`.
- `GuardianSettings` now provides `groq_api_key`, `memgraph_host/port`, `qdrant_host/port`, `embedding_model`.

## Next Immediate Execution Steps
1. An Agent (langgraph_orchestrator) needs to create the LangGraph StateGraph with Gatekeeper + Red Team agents.
2. Wire the Hybrid Retriever as the context provider into the Gatekeeper's reasoning node.
3. Implement Langfuse `@observe()` instrumentation on the graph nodes.

## Hardware & Environment Constraints
- **LLM Provider**: **Groq**. All AI inference MUST run on Groq.
- **Secrets Management**: All API keys MUST be in `backend/.env`.
