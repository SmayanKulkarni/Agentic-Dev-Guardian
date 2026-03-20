# Implementation Plan: AI Developer Governance & Codebase Evaluator (The Fusion Project)

## Goal Description
To build a highly optimized, real-world multi-agent system that autonomously evaluates, tests, and governs AI-generated code (e.g., from Copilot, Cursor, or internal agents) against a **proprietary codebase**. *(Definition: A company's private, internal source code repository. Since general AI models like Groq or Claude haven't been trained on a company's confidential code, they don't know how it is structured unless we use a system like this to teach them).*

The system eliminates hallucinations and subtle regressions by relying on a deterministic **AST-based Knowledge Graph** *(Definition: A mathematical map of the code where functions, classes, and variables are "Nodes", and their structural relationships like `CALLS` or `INHERITS_FROM` are the connecting "Edges").* 

Combined with semantic vector search, this dual approach (GraphRAG) ensures AI code is safe, architecturally consistent, and well-tested before merging.

## Core Technology Stack
- **Event Streaming**: Apache Kafka
- **AST Parsing & Chunking**: Tree-sitter + CocoIndex (Deterministic semantic extraction)
- **Knowledge Graph Database**: Memgraph (In-memory graph database to map exact codebase structures, e.g. "What breaks if I change this function?").
- **Vector Database**: Qdrant (Semantic code representations). *Note: Modern GraphRAG systems require BOTH a graph DB and a vector DB working together. Qdrant handles "fuzzy" semantic questions ("Which file calculates checkout tax?"), and Memgraph handles the rigid structural mapping.*
- **Agent Orchestration**: LangGraph (Cyclic, stateful multi-agent workflows)
- **LLMOps Governance**: Langfuse (Observability, token tracking, evaluation scoring)
- **LLM Inference Provider**: **Groq**. Utilized for ultra-low latency, blazing-fast inference required for real-time GraphRAG structural evaluations and agent reasoning loops.
- **Secrets Management**: All sensitive API keys (e.g., `GROQ_API_KEY`) and authentication logic MUST be isolated strictly within the `backend/.env` file.

---

## Strict Phased Execution Plan
To prevent AI hallucination and scope-creep, the implementation MUST strictly follow this exact 4-phase sequence. Agents must ONLY build components documented under their assigned Phase.

### Phase 1: Core Python Package & AST Parsers
- **Objective**: Establish the foundational CLI scaffolding and the deterministic code-parsing engine.
- **Components**:
  - `pyproject.toml` (managed via `Poetry`/`pip`) with fixed dependencies (Typer, Pydantic, Tree-sitter, Langfuse, Groq).
  - The `src/dev_guardian` module layout.
  - A Typer CLI interface (e.g., `guardian index`, `guardian evaluate`).
  - The `Tree-sitter` wrapper classes that ingest Python code and deterministically extract AST Nodes (Functions, Classes) and Edges (Dependencies) to prepare for the Graph DB.
- **Constraints**: No database connections or orchestrations in this phase. Strict PEP-8 and Pydantic validation only.

### Phase 2: Memgraph & Qdrant Integration
- **Objective**: Build the hybrid GraphRAG data ingestion and retrieval pipelines.
- **Components**:
  - `Memgraph` Cypher query functions to inject the AST Nodes/Edges.
  - `Qdrant` HNSW vector embeddings injection for the semantic layer (using the Groq embeddings API).
  - The **GraphRAG FGA (Fine-Grained Access)** logic: Every retrieval query MUST be hardcoded to enforce `WHERE node.clearance <= $user_clearance` based on metadata tags to protect restricted proprietary code contexts.
  - A unified "Hybrid Retriever" class that queries both DBs and merges the context.

### Phase 3: LangGraph Agent Workflows
- **Objective**: Instantiate the multi-agent cyclic reasoning orchestration.
- **Components**:
  - **Gatekeeper Agent**: Reviews the incoming PR Diff + Hybrid GraphRAG Context to look for architectural violations.
  - **Red Team Tester Agent**: An adversarial agent that uses the GraphRAG relationships to write deterministic PyTest edge-cases specifically aimed at breaking the PR logic.
  - **LangGraph State Logic**: Implement `TypedDict` workflow states and conditional edges chaining the Red Team and Gatekeeper together.
  - **LLMOps**: Instrument the Graph nodes with Langfuse `@observe()` to track Groq token/latency economics and output DLP masks to prevent secret leakage.

### Phase 4: MCP Server Integration
- **Objective**: Wrap the engine in Anthropic's Model Context Protocol (MCP) to enable immediate IDE Shift-Left governance.
- **Components**:
  - An `mcp_server.py` entry point utilizing the official `mcp` Python SDK (FastMCP or stdio bindings).
  - `@mcp.tool()` wrapper functions that expose `query_guardian_graph()` and `evaluate_local_diff()` directly to the developer's Claude Desktop / IDE instance.
  - Dynamic Context Injection via `@mcp.resource()` to serve real-time repository security guidelines to the IDE.

---

## Security Guardrails & Hard Constraints
- **Agentic Least Privilege (JIT)**: Agents operate strictly on temporary Just-In-Time Read-Only tokens scoped to the PR diff.
- **Data Minimization Edge**: The system parses the proprietary application code locally via AST math. We NEVER send raw gigabytes of proprietary code to Groq to "build" the grid. The LLM is only utilized for final graph retrieval reasoning.

---

## Verification Plan
### Automated Tests
- Unit tests for the Tree-sitter to Memgraph ingestion pipeline using dummy code repositories.
- Mock PyTest executions to ensure generated adversarial code paths correctly test for unhandled exceptions.
- LangGraph execution simulations with synthetic user clearance IDs to strictly verify the Cypher FGA query blocks access to unauthorized modules.

### Manual Verification
- Testing the `dev_guardian` PyPI package inside a test repository, ensuring the Local IDE successfully queries the MCP Server in real-time.
