"""
Migration Pattern Registry.

Architecture Blueprint Reference: Phase 5.1 — Self-Healing Codebase Maintenance.

Maps human-readable pattern keys to Kùzu Cypher query templates that
deterministically identify all impacted AST nodes for a given migration.
Each pattern returns a homogenous list of {name, file_path, node_type, reason}.
"""

from __future__ import annotations

from typing import Any

# ── Each entry maps a pattern key → {description, cypher, batch_strategy}
# $repo_path is substituted at query time.
#
# `add-type-hints` and `remove-global-state` were dropped: their queries
# filtered on `return_type`/`scope`/`is_mutable`, properties the AST parser
# has never written, so Memgraph silently matched nothing and Kùzu errors
# outright on an undeclared property (`Binder exception: Cannot find property`).
MIGRATION_PATTERNS: dict[str, dict[str, Any]] = {
    "migrate-pydantic-v1-to-v2": {
        "description": "Find all classes inheriting from pydantic.BaseModel and using v1-only APIs (validators, Config class).",
        "cypher": """
MATCH (n:ASTNode)-[:INHERITS_FROM]->(base:ASTNode)
WHERE base.name CONTAINS 'BaseModel'
RETURN n.name AS name,
       n.file_path AS file_path,
       n.node_type AS node_type,
       'pydantic_basemodel_subclass' AS reason
ORDER BY n.file_path
""",
        "batch_strategy": "leaf_first",  # migrate validators before models
    },
    "migrate-flask-to-fastapi": {
        "description": "Find all route handler functions decorated with @app.route or Flask Blueprint routes.",
        "cypher": """
MATCH (decorator:ASTNode)-[:DECORATES]->(n:ASTNode)
WHERE decorator.name CONTAINS 'route'
RETURN n.name AS name,
       n.file_path AS file_path,
       n.node_type AS node_type,
       'flask_route_handler' AS reason
ORDER BY n.file_path
""",
        "batch_strategy": "by_file",
    },
    "deprecate-function": {
        "description": "Find all callers of a specific function (blast radius for deprecation).",
        "cypher": """
MATCH (caller:ASTNode)-[:CALLS]->(target:ASTNode {name: $function_name})
RETURN caller.name AS name,
       caller.file_path AS file_path,
       caller.node_type AS node_type,
       'calls_deprecated_function' AS reason
ORDER BY caller.file_path
""",
        "batch_strategy": "by_file",
    },
}


def list_patterns() -> list[dict[str, str]]:
    """Return a user-friendly list of available migration patterns."""
    return [
        {"key": key, "description": meta["description"]}
        for key, meta in MIGRATION_PATTERNS.items()
    ]


def get_pattern(key: str) -> dict[str, Any] | None:
    """Retrieve a migration pattern by key, or None if not found."""
    return MIGRATION_PATTERNS.get(key)
