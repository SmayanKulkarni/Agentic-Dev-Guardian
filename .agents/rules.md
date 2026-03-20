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

By following these rules, you will prevent architectural drift and maintain a clean, agent-optimized workspace.
