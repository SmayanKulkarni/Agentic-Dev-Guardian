"""
Capability Clusters for JIT MCP Tool Loading.

Each cluster module exposes a `register(mcp)` and `unregister(mcp)` function
that dynamically binds/unbinds its tools from the FastMCP server instance,
followed by a `notifications/tools/list_changed` event.
"""

from dev_guardian.capability_clusters.core import CLUSTER_REGISTRY

__all__ = ["CLUSTER_REGISTRY"]
