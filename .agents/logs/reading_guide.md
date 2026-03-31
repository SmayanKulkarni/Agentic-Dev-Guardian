# Dev Guardian Codebase Reading Guide

To understand the core architecture and flow of the Dev Guardian codebase, it is highly recommended to read the files in a bottom-up approach. Start with the foundational data structures and configurations, move to the data storage and external integrations, then dive into the core business logic (agents and capabilities), and finally review the entry points.

## 1. Project Configuration & Infrastructure
These files define the environment, dependencies, and configuration info.
- `backend/pyproject.toml`
- `backend/docker-compose.yml`
- `backend/src/dev_guardian/core/config.py`
- `backend/src/dev_guardian/core/logging.py`

## 2. Code Parsing (The Data Ingestion Layer)
Understanding how the system parses and models code into an AST is crucial before looking at the database or LLM logic.
- `backend/src/dev_guardian/parsers/models.py`
- `backend/src/dev_guardian/parsers/ast_parser.py`

## 3. GraphRAG & Vector Storage (The Memory Layer)
These modules handle interactions with the graph database (Memgraph) and vector database (Qdrant), creating the hybrid retrieval architecture.
- `backend/src/dev_guardian/graphrag/memgraph_client.py`
- `backend/src/dev_guardian/graphrag/qdrant_client.py`
- `backend/src/dev_guardian/graphrag/vector_manager.py`
- `backend/src/dev_guardian/graphrag/hybrid_retriever.py`

## 4. Agentic Workflows (The Brain)
This is the core business logic powered by LangGraph. Start with the state definition and graph orchestration before diving into individual agent nodes.
- `backend/src/dev_guardian/agents/state.py` (Defines the LangGraph TypedDict State)
- `backend/src/dev_guardian/agents/graph.py` (The main LangGraph orchestration)
- `backend/src/dev_guardian/agents/refactor_graph.py` & `backend/src/dev_guardian/agents/sre_graph.py` (Specialized sub-graphs)

*Individual Agent Nodes (Read based on your specific interest)*:
- `backend/src/dev_guardian/agents/incident_triager.py`
- `backend/src/dev_guardian/agents/red_team.py`
- `backend/src/dev_guardian/agents/pattern_translator.py`
- `backend/src/dev_guardian/agents/gatekeeper.py`
- `backend/src/dev_guardian/agents/blueprint_validator.py`
- `backend/src/dev_guardian/agents/hotfix_scribe.py`
- `backend/src/dev_guardian/agents/migration_scribe.py`
- `backend/src/dev_guardian/agents/refactor_planner.py`
- `backend/src/dev_guardian/agents/refactor_patterns.py`
- `backend/src/dev_guardian/agents/remediation.py`
- `backend/src/dev_guardian/agents/sandbox_reproducer.py`

## 5. Capability Clusters (High-Level Skill Groupings)
These group the agents into specific functional sets.
- `backend/src/dev_guardian/capability_clusters/core.py`
- `backend/src/dev_guardian/capability_clusters/codebase_intelligence.py`
- `backend/src/dev_guardian/capability_clusters/incident_response.py`
- `backend/src/dev_guardian/capability_clusters/pr_governance.py`
- `backend/src/dev_guardian/capability_clusters/self_healing.py`

## 6. Documentation Engine
Modules responsible for generating autonomous, LLM-narrated architectural docs and ADRs.
- `backend/src/dev_guardian/docs/structure_explainer.py`
- `backend/src/dev_guardian/docs/adr_generator.py`
- `backend/src/dev_guardian/docs/wiki_builder.py`

## 7. Entry Points (The Interfaces)
Finally, review how everything is tied together and exposed to the user or other systems.
- `backend/src/dev_guardian/cli.py` (Command Line Interface using Typer)
- `backend/src/dev_guardian/mcp_server.py` (Model Context Protocol server)
