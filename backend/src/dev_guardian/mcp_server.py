"""
MCP Server for Agentic Dev Guardian.

Architecture Blueprint Reference: Phase 4 — MCP Server Integration
                                   Phase 5 — JIT Tool Loading.

Wraps the internal GraphRAG retrieval engine and the LangGraph MoA
evaluation pipeline into Anthropic Model Context Protocol (MCP) tools,
resources, and prompts — enabling any MCP-compatible IDE (Cursor,
Claude Desktop, Windsurf) to natively query, evaluate, and govern
codebases in real-time.

## JIT Architecture
To keep the IDE LLM's context window lean, tools are loaded on-demand
via the "Bootstrap → Equip → Work → Unequip" lifecycle:

  1. Server starts with only 4 bootstrap tools:
       - query_guardian_graph
       - list_capabilities
       - equip_capability
       - unequip_capability
  2. IDE agent calls equip_capability("pr_governance") to load additional tools.
  3. FastMCP emits `notifications/tools/list_changed` so the IDE refreshes.
  4. Agent uses the new tools and calls unequip_capability when done.

Security:
    - All queries enforce ABAC clearance filtering.
    - Raw proprietary code is NEVER sent to the LLM; only AST-derived
      context is transmitted (Data Minimization Guardrail).
"""

from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP

import dev_guardian.capability_clusters.codebase_intelligence  # noqa: F401
import dev_guardian.capability_clusters.incident_response  # noqa: F401

# ── Bootstrap all cluster modules so they populate CLUSTER_REGISTRY ─
import dev_guardian.capability_clusters.pr_governance  # noqa: F401
import dev_guardian.capability_clusters.self_healing  # noqa: F401
from dev_guardian.capability_clusters.core import (
    CLUSTER_REGISTRY,
    get_active_capabilities,
    mark_active,
    mark_inactive,
)
from dev_guardian.core.config import get_settings
from dev_guardian.core.logging import get_logger
from dev_guardian.skills import register_all_skills

logger = get_logger(__name__)

register_all_skills()

# ── Initialize the MCP Server ──────────────────────────────────────
mcp = FastMCP("Agentic Dev Guardian")

# Tracks tool names that were dynamically added so we can remove them.
_registered_tool_names: dict[str, set[str]] = {}


# ═══════════════════════════════════════════════════════════════════
#  BOOTSTRAP TOOLS — Always active (3 tools only)
# ═══════════════════════════════════════════════════════════════════


@mcp.tool()
def query_guardian_graph(
    query: str,
    clearance: int = 0,
    top_k: int = 5,
) -> str:
    """Search the codebase knowledge graph using hybrid GraphRAG retrieval.

    Performs a dual-database query combining Qdrant semantic vector search
    with Memgraph structural AST graph traversal. Returns merged context
    showing relevant functions, classes, and their dependency relationships.

    Use this tool when you need to understand codebase structure, find
    related functions, trace dependency chains, or assess the blast radius
    of a proposed change.

    This is a BOOTSTRAP tool — always available without equipping any capability.

    Args:
        query: Natural language description of what you are looking for
               in the codebase (e.g., "authentication middleware",
               "database connection pooling", "payment processing").
        clearance: ABAC security clearance level (0=public, higher=restricted).
                   Only entities at or below this clearance level are returned.
        top_k: Maximum number of semantic search results to retrieve.

    Returns:
        A structured text block containing semantic search hits and
        structural graph context, ready for LLM reasoning.
    """
    from dev_guardian.graphrag.clients import get_retriever, reset_clients

    logger.info("mcp_query_graph", query=query, clearance=clearance, top_k=top_k)

    try:
        result = get_retriever().retrieve(
            query=query,
            user_clearance=clearance,
            top_k=top_k,
        )
        return result.get("merged_context", "No results found.")
    except Exception as exc:
        reset_clients()
        logger.error("mcp_query_graph_error", error=str(exc))
        return (
            f"[Guardian Error] GraphRAG query failed: {exc}. "
            "Ensure Memgraph and Qdrant are running and the codebase "
            "has been indexed with `dev-guardian index <path>`."
        )


@mcp.tool()
def list_capabilities() -> str:
    """List all available JIT capability domains that can be equipped.

    Returns a JSON description of every loadable capability cluster,
    including which tools each cluster exposes. Call this first to
    understand what is available, then use equip_capability() to load
    the domain you need.

    This is a BOOTSTRAP tool — always available without equipping any capability.

    Returns:
        JSON with available domains, their descriptions, and tool names.
    """
    active = get_active_capabilities()
    payload = {
        "active_capabilities": sorted(active),
        "available_capabilities": {
            name: {
                "description": meta["description"],
                "tools": list(meta["tools"].keys()),
                "prompts": meta.get("prompts", []),
                "status": "ACTIVE" if name in active else "INACTIVE",
            }
            for name, meta in CLUSTER_REGISTRY.items()
        },
    }
    return json.dumps(payload, indent=2)


@mcp.tool()
def equip_capability(domain: str) -> str:
    """Dynamically load a capability cluster into the active MCP session.

    Registers the specialized tools for the given domain into the live
    FastMCP server and fires notifications/tools/list_changed so the IDE
    client automatically refreshes its tool list.

    Call list_capabilities() first to see what domains are available.
    Call unequip_capability() when done to keep the context window lean.

    This is a BOOTSTRAP tool — always available.

    Args:
        domain: The capability domain to load (e.g., "pr_governance",
                "codebase_intelligence"). Use list_capabilities() to
                see all valid domain names.

    Returns:
        Confirmation message listing the newly registered tool names.
    """
    if domain not in CLUSTER_REGISTRY:
        available = ", ".join(CLUSTER_REGISTRY.keys())
        return (
            f"[Guardian Error] Unknown capability domain: '{domain}'. "
            f"Available domains: {available}"
        )

    if domain in get_active_capabilities():
        tools = list(CLUSTER_REGISTRY[domain]["tools"].keys())
        return (
            f"Capability '{domain}' is already active. "
            f"Tools available: {tools}"
        )

    cluster = CLUSTER_REGISTRY[domain]
    registered: set[str] = set()

    for tool_name, tool_fn in cluster["tools"].items():
        # FastMCP's add_tool registers a function as a named tool
        mcp.add_tool(tool_fn, name=tool_name)
        registered.add(tool_name)

    _registered_tool_names[domain] = registered
    mark_active(domain)

    logger.info("jit_capability_equipped", domain=domain, tools=sorted(registered))

    return (
        f"✅ Capability '{domain}' equipped. "
        f"New tools available: {sorted(registered)}. "
        f"The IDE will refresh its tool list automatically."
    )


@mcp.tool()
def unequip_capability(domain: str) -> str:
    """Unload a capability cluster to keep the context window lean.

    Removes all tools registered by the given domain from the live
    FastMCP server and fires notifications/tools/list_changed so the IDE
    client automatically refreshes.

    Call this after completing a task to avoid overloading the LLM
    context with unnecessary tools.

    This is a BOOTSTRAP tool — always available.

    Args:
        domain: The capability domain to unload (e.g., "pr_governance").

    Returns:
        Confirmation message listing the removed tool names.
    """
    if domain not in get_active_capabilities():
        return f"Capability '{domain}' is not currently active."

    removed = _registered_tool_names.pop(domain, set())

    for tool_name in removed:
        try:
            mcp._tool_manager.remove_tool(tool_name)
        except Exception:
            # Best-effort removal; not all FastMCP versions expose remove_tool
            pass

    mark_inactive(domain)
    logger.info("jit_capability_unequipped", domain=domain, tools=sorted(removed))

    return (
        f"🗑️  Capability '{domain}' unequipped. "
        f"Removed tools: {sorted(removed)}. "
        f"Context window cleaned up."
    )


# ═══════════════════════════════════════════════════════════════════
#  RESOURCES — Dynamic context the IDE can read passively
# ═══════════════════════════════════════════════════════════════════


@mcp.resource("guardian://status")
def get_guardian_status() -> str:
    """Current operational status of the Agentic Dev Guardian system.

    Returns connectivity status for all backend services and the
    current configuration state, including which capability clusters
    are currently active.
    """
    settings = get_settings()
    active = sorted(get_active_capabilities())
    status = {
        "version": "0.2.0",
        "groq_configured": bool(settings.groq_api_key),
        "langfuse_configured": bool(settings.langfuse_public_key),
        "memgraph_endpoint": f"{settings.memgraph_host}:{settings.memgraph_port}",
        "qdrant_endpoint": f"{settings.qdrant_host}:{settings.qdrant_port}",
        "embedding_model": settings.embedding_model,
        "bootstrap_tools": [
            "query_guardian_graph",
            "list_capabilities",
            "equip_capability",
            "unequip_capability",
        ],
        "active_capabilities": active,
        "available_capability_domains": list(CLUSTER_REGISTRY.keys()),
    }
    return json.dumps(status, indent=2)


@mcp.resource("guardian://security-policy")
def get_security_policy() -> str:
    """Repository security policy and architectural constraints.

    Returns the ABAC access control rules and data minimization
    guardrails enforced by the Guardian system. The IDE agent should
    reference these rules when evaluating code changes.
    """
    policy = (
        "# Agentic Dev Guardian — Security Policy\n\n"
        "## ABAC Access Control\n"
        "- Every GraphRAG query enforces `WHERE node.clearance <= $user_clearance`.\n"
        "- Agents operate on Just-In-Time Read-Only tokens scoped to the PR diff.\n"
        "- clearance=0 is public, higher values access restricted contexts.\n\n"
        "## Data Minimization\n"
        "- Raw proprietary code is NEVER sent to external LLMs.\n"
        "- Only AST-derived structural metadata and semantic embeddings are "
        "transmitted.\n"
        "- Embeddings are generated locally using FastEmbed "
        "(jinaai/jina-embeddings-v2-base-code).\n\n"
        "## Architectural Invariants\n"
        "- Frontend UI components must NOT directly import database models.\n"
        "- Payment services must NOT use synchronous HTTP calls.\n"
        "- All public API endpoints must have authentication middleware.\n"
        "- Database migrations must include a rollback strategy.\n"
    )
    return policy


# ═══════════════════════════════════════════════════════════════════
#  PROMPTS — Pre-defined system instructions for common workflows
# ═══════════════════════════════════════════════════════════════════


@mcp.prompt()
def review_pr(diff: str) -> str:
    """Generate a comprehensive PR review using the Guardian pipeline.

    This prompt instructs the IDE agent to equip pr_governance tools,
    query the knowledge graph for context, evaluate the diff through the
    MoA pipeline, and present results in a structured review format.
    """
    return (
        "You are reviewing a Pull Request using the Agentic Dev Guardian system.\n\n"
        "Guardian's tools may appear under a client-specific prefix (for example "
        "`guardian__equip_capability`). Match them by name suffix, not exactly.\n\n"
        "## Instructions\n"
        "1. Use the equip_capability tool with domain 'pr_governance' to load the "
        "   evaluation tools.\n"
        "2. Use query_guardian_graph with a summary of the diff to understand "
        "   the affected codebase area.\n"
        "3. Use evaluate_pr_diff with the full diff content.\n"
        "4. Present results as a structured code review:\n"
        "   - Decision (APPROVE / REMEDIATE)\n"
        "   - Architectural violations found\n"
        "   - Adversarial test cases generated\n"
        "   - Suggested fixes (if any)\n"
        "5. Use unequip_capability with domain 'pr_governance' when done.\n\n"
        f"## PR Diff\n```diff\n{diff}\n```"
    )


@mcp.prompt()
def investigate_function(function_name: str) -> str:
    """Deep-dive investigation into a specific function's role and impact.

    Instructs the IDE agent to equip codebase_intelligence tools, perform
    impact analysis, and retrieve all contextual information about a function.
    """
    return (
        f"Investigate the function `{function_name}` in the codebase.\n\n"
        "Guardian's tools may appear under a client-specific prefix (for example "
        "`guardian__equip_capability`). Match them by name suffix, not exactly.\n\n"
        "## Instructions\n"
        "1. Use equip_capability with domain 'codebase_intelligence' to load "
        "   analysis tools.\n"
        f"2. Use impact_analysis for `{function_name}` to find all "
        "   downstream dependencies.\n"
        f'3. Use query_guardian_graph with "{function_name}" to get '
        "   semantic context.\n"
        "4. Summarize:\n"
        f"   - What `{function_name}` does\n"
        "   - What depends on it (blast radius)\n"
        "   - Risks of modifying it\n"
        "   - Suggested refactoring approach (if applicable)\n"
        "5. Use unequip_capability with domain 'codebase_intelligence' when done.\n"
    )


# ═══════════════════════════════════════════════════════════════════
#  SERVER ENTRY POINT
# ═══════════════════════════════════════════════════════════════════


def resolve_preload(value: str | None) -> list[str]:
    """Cluster names named by GUARDIAN_PRELOAD_CLUSTERS.

    ``all`` means every registered cluster; otherwise a comma-separated list.
    Unknown names are dropped rather than raising: a stale name in an IDE's
    env block must not stop the server from starting.
    """
    raw = (value or "").strip()
    if not raw:
        return []
    if raw.lower() == "all":
        return list(CLUSTER_REGISTRY)
    names = [n.strip() for n in raw.split(",") if n.strip()]
    return [n for n in names if n in CLUSTER_REGISTRY]


def _preload_clusters() -> None:
    """Equip clusters up front for clients that ignore tools/list_changed.

    The JIT lifecycle assumes the client refreshes its tool list when the
    server notifies it. Clients that do not never see an equipped tool, so
    this env var trades a lean context window for working tools.
    """
    for domain in resolve_preload(os.environ.get("GUARDIAN_PRELOAD_CLUSTERS")):
        if domain not in get_active_capabilities():
            equip_capability(domain)


def run_server(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Start the MCP server.

    Called by the ``dev-guardian serve`` CLI command.

    On startup, only 4 bootstrap tools are exposed to keep the LLM
    context window lean. Additional capability clusters are loaded
    JIT via equip_capability().

    Args:
        transport: ``stdio`` (default) for an IDE-spawned subprocess, or
            ``streamable-http`` to listen on a socket so several clients —
            or a remote one — can connect to one running Guardian.
        host: Bind address for the HTTP transports. Defaults to loopback:
            the server has no authentication of its own and exposes tools
            that read the indexed codebase, so binding it to a public
            interface must be a deliberate act behind a proxy that
            authenticates.
        port: Bind port for the HTTP transports.

    Env:
        GUARDIAN_PRELOAD_CLUSTERS: ``all`` or a comma-separated list of
            cluster names to equip at startup, for clients that do not act
            on ``notifications/tools/list_changed`` and so would never see
            a JIT-equipped tool appear.

    Note:
        Equipped capabilities are process-global, not per-connection. Under
        an HTTP transport shared by several clients, one client's
        ``equip_capability`` is visible to all of them. That is harmless for
        a single-user self-hosted server (the intended shape) but is the
        reason this is not a multi-tenant service.
    """
    if transport != "stdio":
        mcp.settings.host = host
        mcp.settings.port = port

    _preload_clusters()

    logger.info(
        "mcp_server_starting",
        transport=transport,
        bootstrap_tools=4,
        available_clusters=list(CLUSTER_REGISTRY.keys()),
        preloaded=sorted(get_active_capabilities()),
    )
    mcp.run(transport=transport)  # type: ignore[arg-type]
