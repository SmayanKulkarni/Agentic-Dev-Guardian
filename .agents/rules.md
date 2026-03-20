# Codebase Guidelines for AI Agents

Welcome to the Fusion Project repository. As an AI Agent (Antigravity, Copilot, or Cursor), you MUST adhere to the following rules when navigating, planning, or editing this codebase:

## 1. Directory Strictness
- **Logic vs. Prompts**: ALL prompt templates must be stored in `backend/prompts/`. Never hardcode multiline LLM instructions inside the Python logic in `backend/agents/`.
- **Infrastructure**: All Docker Compose, Terraform, and system setup scripts live in `infrastructure/`.
- **Evaluation**: All test scripts for the agents go in `evaluation/scripts/`, not in the main backend scope.

## 2. Modularity & Token Limits
- When generating code, keep files small and hyper-focused. If a file exceeds 300 lines, refactor it by extracting helper functions into `backend/core/`.
- Do not output monolithic classes.

## 3. Technology Alignment
- **Event Bus**: We use Apache Kafka. Do not assume or import RabbitMQ or Redis Pub/Sub.
- **GraphRAG**: We use Memgraph + Tree-sitter. Use Cypher syntax for all graph queries.
- **Agent Orchestration**: We use LangGraph in Python. Ensure all agent workflows follow the state-graph methodology.
- **LLMOps**: Instrument all LLM calls with Langfuse decorators.

## 4. Agent Memory & Logging Protocol
- **ABSOLUTE GROUND TRUTH**: You MUST read `.agents/memory/architecture_blueprint.md`. This document contains the exhaustive, finalized mathematical and structural plan for the project. You are **strictly forbidden** from scope-creeping, inventing new features, or deviating from this blueprint. Any drift is considered a failure.
- **MANDATORY READ (COLD START CONTEXT)**: You are likely entering this workspace without previous chat history. Before writing *any* code, you MUST aggressively read `.agents/memory/context.md` (to know the active Phase), and the latest entries in `.agents/logs/implementation_log.md` (to understand exactly what functions, schemas, and classes from the previous phase you need to interface with).
- **MANDATORY WRITE (EXHAUSTIVE LOGS)**: After completing any coding phase, you MUST append a timestamped log to `.agents/logs/implementation_log.md`. This log must be **exhaustively detailed**. You must document exactly what code was written, list every fundamental Python function created, describe what they do, and explicitly map them backwards to what component of the `architecture_blueprint.md` they satisfy.
- **MANDATORY WRITE (HUMAN IN THE LOOP)**: You MUST update `.agents/memory/human_in_the_loop.md`. You must translate your highly technical code changes into a simple, ground-up summary for the human supervisor, explaining exactly what structural changes were made to the codebase and how they impact the overall project.
- **STATE SYNC**: You MUST update `.agents/memory/context.md` to reflect the new state of the architecture so the next agent handling the workspace has perfect context. By strictly enforcing this, we ensure a hive-mind workflow.

By following these rules, you will prevent architectural drift and maintain a clean, agent-optimized workspace.
