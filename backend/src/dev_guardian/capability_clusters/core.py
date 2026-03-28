"""
Core capability cluster registry.

Defines the CLUSTER_REGISTRY that maps capability domain names
to their register/unregister functions and metadata.
"""

from __future__ import annotations

from typing import Any

# ── Live state: tracks which clusters are currently active ──────────
_active_capabilities: set[str] = set()


def get_active_capabilities() -> set[str]:
    return set(_active_capabilities)


def mark_active(name: str) -> None:
    _active_capabilities.add(name)


def mark_inactive(name: str) -> None:
    _active_capabilities.discard(name)


# ── Cluster registry: each entry describes one capability domain ────
# Populated lazily by each cluster module on import.
CLUSTER_REGISTRY: dict[str, dict[str, Any]] = {}
