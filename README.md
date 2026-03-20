# AI Developer Governance & Codebase Evaluator

## Overview
This repository contains a highly optimized, enterprise-grade multi-agent system designed to autonomously evaluate, test, and govern AI-generated code (e.g., from Copilot, Cursor, or internal autonomous agents) against a proprietary codebase. 

By utilizing a cutting-edge hybrid retrieval approach (GraphRAG), the system combines structural codebase understanding with semantic context. It acts as an autonomous Red Team and Quality Gate, dynamically generating adversarial unit tests specifically targeted to break proposed Pull Requests based on the codebase's true architecture.

## 🏗️ Core Architecture
- **Event Bus:** Apache Kafka for streaming Git events and LLM telemetry.
- **GraphRAG Framework:** Code-Graph-RAG.
- **AST Parsing:** Tree-sitter + CocoIndex (Deterministic extraction of the codebase abstract syntax tree).
- **Knowledge Graph:** Memgraph (In-memory, highly performant mapping of dependencies).
- **Semantic Vector Storage:** Qdrant.
- **Agent Orchestration:** LangGraph in Python.
- **LLMOps & Tracing:** Langfuse (Quality gating and token observability).

## 🗂️ Agentic Directory Map
This repository is explicitly structured for AI agents (Antigravity/Copilot) to navigate cleanly without token-window bloat:
- `.agents/`: Holds the global workspace context rules and skills.
- `backend/agents/`: Isolated, stateless Python routing logic for the AI Gatekeeper, Red Team Tester, and Indexer.
- `backend/prompts/`: Explicitly separated `.txt` prompt templates to prevent logic hallucination.
- `evaluation/`: Hosts baseline adversarial datasets and Langfuse scoring scripts. 
- `infrastructure/`: Declarative IaC (Terraform, Docker Compose).

## 🚀 Getting Started
*(Implementation phase pending)*
