# IDE Agent Instructions: LLM Wiki Maintenance

## 1. Initial State Check
When starting work in this repository or handling a new objective, you must **always** read this file, and then immediately orient yourself by reading the project's LLM Wiki located in the central Obsidian vault at:
`/home/smayan/Documents/Obsidian/MCP Vault/Projects/Agentic Dev Guardian/wiki/index.md`

## 2. Wiki Structure Rules
All project LLM wikis maintained in the Obsidian Vault must exactly follow this standard structure:
```
Project Name/
  ├── raw/       (immutable source documents and references)
  ├── wiki/      (markdown pages maintained by IDE agents)
  │   ├── index.md (table of contents for the project)
  │   └── log.md   (append-only record of changes)
```

## 3. Documentation Update Workflow
After **every update to code** that introduces new behavior, alters architecture, or modifies signatures:
1. **Locate the Vault**: Access `/home/smayan/Documents/Obsidian/MCP Vault/Projects/Agentic Dev Guardian/wiki/`.
2. **Update Wiki Constraints**: 
   - Update the relevant existing component pages.
   - **Keep it limited**: DO NOT write too much overlapping content! Ensure each page serves a uniquely scoped purpose. Prevent duplicated information across pages.
3. **Log Changes**: Append a brief, one-line entry to `log.md` with the date, updated component, and high-level change summary.
4. **Index Verification**: Update `index.md` ONLY if you created entirely new pages.
5. **No Touching Raw**: Never modify anything in the `raw/` folder under any circumstance.
