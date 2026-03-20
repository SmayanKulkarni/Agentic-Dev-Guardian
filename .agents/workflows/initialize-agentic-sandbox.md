---
description: Initialize a flawless Agentic Sandbox environment with rules, memory tracking, skills, and execution logs for any new coding project.
---

# Agentic Sandbox Initialization Workflow

This workflow sets up the gold-standard Hive-Mind agentic working environment designed to eliminate AI hallucination, scope-creep, and context-loss during complex repository execution.

**// turbo-all**
## 1. Create the Sandbox Directory Structure
Run the following bash command to create the necessary isolation folders for the agent ecosystem:
`mkdir -p .agents/memory .agents/logs .agents/skills .agents/workflows`

## 2. Establish the Absolute Rules (`.agents/rules.md`)
Create the global `.agents/rules.md` file with the following strict adherence protocols. In your prompt, instruct all future executing agents to NEVER deviate from them:
- **ABSOLUTE GROUND TRUTH:** Agents MUST read `.agents/memory/architecture_blueprint.md`. No scope-creeping, hallucination, or inventing unapproved features allowed.
- **MANDATORY READ:** Read `.agents/memory/context.md` before coding to understand the active Execution Phase.
- **EXHAUSTIVE LOGS:** After a coding phase, append a strictly exhaustive, function-level technical update to `.agents/logs/implementation_log.md` explicitly mapping back to the blueprint.
- **HUMAN IN THE LOOP:** Translate structural code changes into simple, macro-level updates in `.agents/memory/human_in_the_loop.md` for human supervision.

## 3. Establish the Memory Headers
Initialize the following baseline memory and logging templates explicitly via `write_to_file`:
- **`context.md`** -> A markdown file tracking "Current Phase", "Status", and "Next Immediate Execution Steps", as well as "Hardware/Secrets Constraints".
- **`implementation_log.md`** -> A markdown file containing a strict header instructing agents to leave exhaustive, timestamped technical details that map backwards to the system architecture.
- **`human_in_the_loop.md`** -> A markdown file tracking the macroscopic "Current Project State" and bottom-up structural updates for the Human supervisor without raw PR diffs.

## 4. Define the Architecture Strategy
Ask the user what specific enterprise software system they are trying to build. Work with them to draft a highly granular, strict Phased Implementation Plan that explicitly sandboxes specific features into rigid chronological execution phases (e.g., Phase 1, Phase 2). Once they approve it, save it exclusively to `.agents/memory/architecture_blueprint.md`.

## 5. Instantiate the Skill Roster
Based strictly on the architecture blueprint you just drafted, identify what distinct technical domains exist. Dynamically create highly specialized Agent Personas in `.agents/skills/[role_name]/SKILL.md` (e.g. `frontend_architect`). Each skill file MUST have stringent boundary definitions (e.g., "You only write React components, you NEVER touch the Database").

## 6. Execution Ready
Notify the user that the isolated Hive-Mind sandbox has been successfully initialized. Ask the user for permission to invoke the first skill to begin Phase 1 of the architecture blueprint.
