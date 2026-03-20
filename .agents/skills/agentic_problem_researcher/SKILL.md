---
name: Advanced Agentic AI Problem Researcher
description: Deep researches the web to identify complex, real-world problems in technical domains that can be solved using Advanced Agentic AI frameworks and architectures, and conceptualizes them into full-stack project ideas.
---

# Advanced Agentic AI Problem Researcher

This skill equips the agent with the methodology to conduct deep, targeted web research to uncover intricate, real-world problems within technical domains. The primary goal is to find general, difficult technical challenges. These problems do not necessarily need to be AI or Agentic AI problems natively. Instead, they should be complex scenarios that can be elegantly and powerfully solved by applying Advanced Agentic AI frameworks (e.g., multi-agent collaboration, planning, self-reflection) alongside advanced modern distributed architectures (e.g., Kafka, Cloud Services, LLMOps, Event-Driven Systems).

You will output these findings as tangible, full-stack project blueprints.

## 🎯 Objective
To identify, analyze, and conceptualize complex, general technical problems that can be solved via a combination of Agentic AI and advanced modern technologies, turning them into actionable full-stack project proposals.

## 🛠️ Execution Steps

### 1. Identify and Narrow Down Target Domains
- **Action**: Use the `search_web` tool to explore current bottlenecks, pain points, and trends in hard technical domains (e.g., Cloud Architecture, Cybersecurity, Data Engineering, SRE/DevOps, FinTech, Bio-informatics).
- **Focus Mechanism**: Skip surface-level problems (e.g., "writing emails" or "basic customer support chatbots"). Focus on areas requiring dynamic adaptation, multi-step reasoning, and integration with varied APIs/systems.

### 2. Deep Research for Problem Discovery
- **Action**: Dive into technical forums, research papers, specialized subreddits (e.g., r/devops, r/MachineLearning), HackerNews, and GitHub issue trackers. You can use the `browser_subagent` or `search_web` combined with `read_url_content`.
- **Criteria for Selection**:
  - **High Complexity**: Cannot be solved with a single prompt. Requires an agentic workflow (planning, execution, reflection).
  - **Real-World Impact**: Addresses a genuine, expensive, or time-consuming pain point for engineers or businesses.
  - **Actionability**: The solution can realistically be built as a full-stack project (Frontend UI, Backend Services, Agent Engine, Data/Memory Layer).

### 3. Analyze and Conceptualize Agentic Interventions
For each discovered problem, construct a conceptual framework for an Agentic AI solution. Define:
- **The Core Problem**: What is the complex issue? Why does traditional software or basic AI fail to solve it?
- **The Agentic Advantage**: Why is a multi-agent system or advanced agentic workflow (like LangGraph, CrewAI, AutoGen) uniquely suited for this?
- **High-Level Architecture**:
  - **Core Technologies**: How advanced technologies like Kafka (event streaming), AWS/GCP (cloud services), and LLMOps (evaluation, tracking) factor into the architecture.
  - **Agent Roles**: (e.g., "Planner Agent", "Code Execution Agent", "Reviewer Agent").
  - **Required Tools/Integrations**: (e.g., Kubernetes API, GitHub API, Web Scrapers, Terraform).
  - **Memory/State Management**: How the context is retained (e.g., Vector DBs, graph databases).
- **Full-Stack Vision**: How this translates into a usable product (e.g., "A modern Next.js dashboard showing real-time agent collaboration on CI/CD pipelines, ingesting real-time logs via Kafka, backed by a scalable Python FASTApi orchestration layer with robust LLMOps monitoring").

### 4. Produce the Project Proposal Artifact
- **Action**: Compile the findings into a structured markdown artifact (e.g., `agentic_project_proposals.md`).
- **Format**: Use the included `report_template.md` (if available in resources) or follow a highly structured format with Executive Summaries, deep-dive problem descriptions, and Mermaid diagrams for the proposed agent workflows.

## 🧰 Tools to Utilize
- `search_web`: Broad discovery of technical domain pain points.
- `read_url_content` / `browser_subagent`: Deep reading of complex technical content.
- `write_to_file`: Documenting the final blueprints and generating architectural diagrams (Mermaid syntax).

## 💡 Inspiration (Examples of "Advanced" Problems)
- **Autonomous SRE / Incident Remediation**: An agent collective that detects production anomalies, reads logs, researches the error, queries the internal codebase, tests a fix in a sandbox, and prepares a patching PR.
- **Intelligent Cloud FinOps Engineer**: Agents that analyze multi-cloud billing, understand the actual infrastructure usage, simulate alternative architectures for cost-saving, and autonomously generate Terraform scripts for the new architecture.
- **Dynamic Security Posture Tester**: A continuous Red Team multi-agent setup that probes a company's external attack surface, chains vulnerabilities together, and automatically writes the corresponding Blue Team monitoring rules.
