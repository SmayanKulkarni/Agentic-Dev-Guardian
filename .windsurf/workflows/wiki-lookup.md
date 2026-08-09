---
description: Dynamically look up knowledge from the Obsidian LLM Wiki vault using the Obsidian MCP
---

# Wiki Lookup Workflow

Use this workflow whenever you need to consult project knowledge, architecture, constraints, or domain context stored in the Obsidian vault.

**Never hardcode paths or assume structure — always discover dynamically.**

---

## Step 1 — Discover available MOCs

Call `mcp7_discover-mocs` with no arguments. This returns all Maps of Content currently in the vault, including the LLM Wiki master index and any project-specific wiki indexes.

Read the results to understand what wikis exist right now.

---

## Step 2 — Read the relevant index

From the MOC list, identify the most relevant index note for the current task and call `mcp7_read-note` on it. The index will list its own child pages — do not assume what those pages are.

---

## Step 3 — Navigate to the specific page(s)

Read the child pages linked from the index that are relevant to the task. Use the titles and descriptions in the index to decide which ones to open — do not guess paths that weren't listed.

If you are unsure which page to open, use `mcp7_search-vault` with a keyword query derived from the task, then read the matching notes.

---

## Step 4 — Apply the knowledge

- Honour any **Hard Limits** or constraints stated in the wiki pages.
- Follow the architecture and module boundaries described.
- Do not invent names, algorithms, or structure that the wiki does not document.
- If a page is stale or contradicts the codebase, flag it but prefer the wiki's intent.
