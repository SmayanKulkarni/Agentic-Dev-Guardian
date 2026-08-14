"""
MCP client contract (ticket 07) — drives the real server over stdio with a
real MCP client, so the JIT capability lifecycle is verified against the
protocol rather than against the implementation's own assumptions.

What this covers:
  * the server starts under an IDE-style spawn and completes `initialize`,
  * `tools/list` exposes exactly the bootstrap tools at startup,
  * `equip_capability` grows the tool list and `unequip_capability` shrinks it,
  * cold start stays inside a budget an IDE will tolerate.

What it cannot cover: whether a given IDE *acts* on the
`notifications/tools/list_changed` it receives. That is client behaviour, not
server behaviour. The server-side guarantee tested here — the tool list really
does change between two `tools/list` calls — is the half Guardian controls, and
a client that re-lists on notification (or on every turn) will observe it.
"""
from __future__ import annotations

import os
import sys
import time

import pytest

# Deliberately *not* marked `integration`: this spawns the server in-process and
# needs neither Memgraph nor Qdrant, so it can gate a release (ticket 08).
mcp_client = pytest.importorskip("mcp.client.stdio")
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

BOOTSTRAP_TOOLS = {
    "query_guardian_graph",
    "list_capabilities",
    "equip_capability",
    "unequip_capability",
}

# An IDE spawns the server on the user's first request; anything past this and
# the integration feels broken. fastembed/ONNX must therefore stay out of
# module import and load lazily inside the tools that need embeddings.
COLD_START_BUDGET_SECONDS = 15.0

_SERVER = StdioServerParameters(
    command=sys.executable,
    args=["-c", "from dev_guardian.mcp_server import run_server; run_server()"],
    # This suite exercises the JIT lifecycle itself, so it opts out of the
    # preload-all default (docs/README) to keep the bootstrap-only assertion
    # meaningful.
    env={**os.environ, "GUARDIAN_PRELOAD_CLUSTERS": "none"},
)


async def _tool_names(session: ClientSession) -> set[str]:
    return {t.name for t in (await session.list_tools()).tools}


@pytest.mark.asyncio
async def test_server_starts_and_exposes_only_bootstrap_tools():
    t0 = time.monotonic()
    async with stdio_client(_SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            elapsed = time.monotonic() - t0
            names = await _tool_names(session)

    assert names == BOOTSTRAP_TOOLS, f"unexpected startup tool set: {names}"
    assert elapsed < COLD_START_BUDGET_SECONDS, f"cold start took {elapsed:.1f}s"


@pytest.mark.asyncio
async def test_equip_then_unequip_changes_the_tool_list():
    async with stdio_client(_SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            before = await _tool_names(session)

            await session.call_tool("equip_capability", {"domain": "pr_governance"})
            equipped = await _tool_names(session)

            await session.call_tool("unequip_capability", {"domain": "pr_governance"})
            after = await _tool_names(session)

    assert equipped > before, "equip_capability added no tools"
    assert after == before, "unequip_capability did not restore the tool list"


@pytest.mark.asyncio
async def test_listing_capabilities_works_before_any_codebase_is_indexed():
    """A freshly spawned server must answer discovery calls even with an empty
    graph — the IDE lists tools long before the user runs `dev-guardian index`."""
    async with stdio_client(_SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("list_capabilities", {})

    text = "".join(getattr(c, "text", "") for c in result.content)
    assert "pr_governance" in text
