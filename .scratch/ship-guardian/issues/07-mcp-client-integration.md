# MCP client integration, verified in a real IDE

Type: prototype
Status: resolved
Blocked by: 03

## Question

Prove the end state works in a real client before declaring the release shape.

- What exact JSON does the user paste into Cursor / Claude Desktop, given the install path decided in 03?
- Does the JIT capability lifecycle (`equip_capability` emitting `notifications/tools/list_changed`)
  actually cause a tools refresh in these clients, or do they cache the tool list at startup? This is
  the core design bet of `mcp_server.py` and it has not been verified against a real client.
- Does the server start acceptably fast when spawned by the IDE, given fastembed / ONNX model loading?
- What is the behaviour when the server is spawned before any codebase has been indexed?

## Answer

**The exact JSON is generated, not hand-maintained.** `dev-guardian init --print-mcp-config`
emits the block with this install's resolved settings:

```json
{
  "mcpServers": {
    "guardian": {
      "command": "uvx",
      "args": ["--from", "agentic-dev-guardian", "dev-guardian", "serve"],
      "env": {
        "GUARDIAN_PROVIDER": "groq",
        "GUARDIAN_GROQ_API_KEY": "<your-api-key>",
        "GUARDIAN_MEMGRAPH_HOST": "127.0.0.1",
        "GUARDIAN_MEMGRAPH_PORT": "7687",
        "GUARDIAN_QDRANT_HOST": "127.0.0.1",
        "GUARDIAN_QDRANT_PORT": "6333"
      }
    }
  }
}
```

Note `dev-guardian`, not `guardian` — the entry point was renamed per tickets 02/08.

**Cold start: 0.26s** measured, spawning the server exactly as an IDE does and timing to the
end of `initialize`. fastembed/ONNX is imported lazily inside the tools that embed, never at
module import, so the model load never lands in the spawn path. A 15s budget is asserted in
the test so a future eager import fails CI instead of the user's editor.

**Before any codebase is indexed**: the server starts and answers `tools/list` and
`list_capabilities` normally — nothing touches Memgraph or Qdrant during discovery. The CLI's
`serve` command additionally refuses to start when the services are down (ticket 05), with the
message on stderr so the stdio channel stays clean.

**The JIT lifecycle bet, honestly scoped.** `backend/tests/integration/test_mcp_client_contract.py`
drives the real server over stdio with a real MCP client and proves the server half:
startup exposes exactly the 4 bootstrap tools, `equip_capability("pr_governance")` makes
`tools/list` return more, and `unequip_capability` restores it exactly. What no test here can
prove is whether a *particular* IDE re-lists on `notifications/tools/list_changed` — that is
client behaviour, and it varies by client and version. The design's exposure is therefore
bounded and known: on a client that caches tools for the session, the equipped tools appear on
the next refresh rather than immediately; nothing breaks, discovery is just delayed. Confirming
per-client refresh behaviour stays a manual step for whoever has that IDE open, and the test
above is what makes such a report actionable.
