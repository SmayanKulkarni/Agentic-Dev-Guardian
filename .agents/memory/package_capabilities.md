# Agentic Dev Guardian: Full Capabilities & Product Vision

This document outlines everything the `agentic-dev-guardian` Python package is capable of doing once Phase 5 is fully implemented. It serves as a reference for the project's ultimate goals and capabilities as a seamlessly installable `pip` package.

## The Core Engine (Phases 1-4)
Before any advanced features work, the user initializes the engine:
1. **`guardian index <path>`**: Deterministically parses an entire local repository into a hybrid Knowledge Graph (Memgraph AST structure + Qdrant semantic vectors). No LLM tokens are wasted on reading files.
2. **`guardian serve`**: Boots the MCP (Model Context Protocol) Server, instantly giving any compliant IDE (Cursor, Claude Desktop, Windsurf) native access to the codebase graph and the agent pipelines.

Once running, the package unlocks the following capabilities:

---

## 1. Shift-Left PR Governance (Phase 1-4 Core)
**How:** `guardian evaluate my.diff` or automatically via the IDE's MCP integration.
**What it does:** Instead of waiting for a senior engineer to review code, developers run code through a local Mixture-of-Agents (MoA) pipeline.
- The **Gatekeeper** checks for architectural rule violations.
- The **Red Team** attempts to break the code.
- The **Supervisor** decides if the code passes.
- The **Remediation Specialist** automatically generates a fixed diff if the code is rejected.

## 2. "Self-Healing" Codebase Refactoring (Phase 5.1)
**How:** `guardian refactor --pattern "migrate-flask-to-fastapi"`
**What it does:** Because the package understands the massive dependency graph, it can autonomously execute huge, multi-file refactoring tasks. Changing a function signature in a base class prompts the Guardian to automatically traverse the graph, find every downstream child file that relies on it, and output a **Comprehensive Step-By-Step Refactoring Blueprint**. The user then hands this flawless Master Plan to their IDE AI to blindly execute the raw code changes file-by-file.

## 3. Automated Incident Response / SRE Sandboxing (Phase 5.2)
**How:** `guardian debug crash.log`
**What it does:** A developer pastes a messy stack trace from production into the terminal or IDE. The Guardian uses GraphRAG to instantly trace the crashed line of code, find the surrounding context, and spawn an isolated Python `Docker` sandbox. It then writes a unit test proving the crash, iteratively rewrites the function until the test passes in the sandbox, and returns a verified patch back to the developer.

## 4. Auto-Generating True Architectural Docs (Phase 5.3)
**How:** `guardian generate-docs`
**What it does:** Most developer documentation goes stale instantly. This package dynamically generates highly accurate Mermaid.js architecture diagrams and markdown documentation by querying the *actual* structural state of the code in Memgraph, ensuring documentation is always perfectly synced with the code.

## 5. Live PII & Taint-Tracking Auditor (Phase 5.4)
**How:** `guardian audit-pii` or an IDE prompt: *"Verify my changes didn't break data privacy."*
**What it does:** Uses the structural Memgraph AST to trace the flow of sensitive variables. It can prove that a variable named `user.social_security_number` is never passed into a public `logger.info()` function or an unencrypted database column, providing cryptographically solid data privacy compliance natively.

## 6. Cloud Cost & FinOps Optimization (Phase 5.5)
**How:** `guardian audit-performance`
**What it does:** The engine scans the data access layer via the structural AST graph to detect hidden financial risks, like "N+1 query" patterns in an ORM, API loops that could cause rate-limiting, or synchronous HTTP calls blocking payment pipelines. It then suggests async or batch-optimized code replacements.

## 7. Autonomous Developer Mentorship (Phase 5.6)
**How:** `guardian mentor [ticket_id/description]` (or via IDE).
**What it does:** A junior developer gets a new ticket and asks the Guardian how to start. The Guardian queries the knowledge graph to find similar existing endpoints, reads the company's architectural security policy, and writes a step-by-step, highly customized implementation guide specifically tailored to the codebase's existing structure.

---

## How Developers Interact With the Package

Developers interact with the `.agents` ecosystem in two seamless ways:
1. **The CLI:** Running `guardian <command>` in their terminal or strapping it directly into their GitHub Actions CI/CD pipeline.
2. **The "Ghost in the IDE":** By running `guardian serve`, every single feature listed above becomes a native tool their IDE's AI assistant can call autonomously. As they type, the IDE silently executes audits in the background, warning them of PII leaks or bad DB queries *before* they even hit save.
