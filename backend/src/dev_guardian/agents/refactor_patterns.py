"""
Migration Pattern Registry.

Architecture Blueprint Reference: Phase 5.1 — Self-Healing Codebase Maintenance.

Maps human-readable pattern keys to Memgraph Cypher query templates that
deterministically identify all impacted AST nodes for a given migration.
Each pattern returns a homogenous list of {name, file_path, node_type, reason}.
"""

from __future__ import annotations

from typing import Any

# ── Each entry maps a pattern key → {description, cypher, batch_strategy}
# $repo_path is substituted at query time.
MIGRATION_PATTERNS: dict[str, dict[str, Any]] = {
    "migrate-pydantic-v1-to-v2": {
        "description": "Find all classes inheriting from pydantic.BaseModel and using v1-only APIs (validators, Config class).",
        "cypher": """
MATCH (n)
WHERE (n.node_type = 'class' AND n.bases CONTAINS 'BaseModel')
   OR (n.node_type = 'function' AND n.decorators CONTAINS 'validator')
   OR (n.node_type = 'class' AND n.name = 'Config' AND EXISTS {
         MATCH (parent)-[:CONTAINS]->(n)
         WHERE parent.bases CONTAINS 'BaseModel'
       })
RETURN n.name AS name,
       n.file_path AS file_path,
       n.node_type AS node_type,
       'pydantic_v1_pattern' AS reason
ORDER BY n.file_path
""",
        "batch_strategy": "leaf_first",  # migrate validators before models
    },
    "migrate-flask-to-fastapi": {
        "description": "Find all route handler functions decorated with @app.route or Flask Blueprint routes.",
        "cypher": """
MATCH (n)
WHERE n.node_type = 'function'
  AND (n.decorators CONTAINS 'route' OR n.decorators CONTAINS 'app.route'
       OR n.decorators CONTAINS 'blueprint')
RETURN n.name AS name,
       n.file_path AS file_path,
       n.node_type AS node_type,
       'flask_route_handler' AS reason
ORDER BY n.file_path
""",
        "batch_strategy": "by_file",
    },
    "add-type-hints": {
        "description": "Find all functions missing type annotations on parameters or return types.",
        "cypher": """
MATCH (n)
WHERE n.node_type = 'function'
  AND (n.return_type IS NULL OR n.return_type = '')
RETURN n.name AS name,
       n.file_path AS file_path,
       n.node_type AS node_type,
       'missing_type_hints' AS reason
ORDER BY n.file_path
""",
        "batch_strategy": "by_file",
    },
    "deprecate-function": {
        "description": "Find all callers of a specific function (blast radius for deprecation).",
        "cypher": """
MATCH (caller)-[:CALLS]->(target {name: $function_name})
RETURN caller.name AS name,
       caller.file_path AS file_path,
       caller.node_type AS node_type,
       'calls_deprecated_function' AS reason
ORDER BY caller.file_path
""",
        "batch_strategy": "by_file",
    },
    "remove-global-state": {
        "description": "Find all module-level mutable variables that could be refactored into dependency injection.",
        "cypher": """
MATCH (n)
WHERE n.node_type = 'variable'
  AND n.scope = 'module'
  AND n.is_mutable = true
RETURN n.name AS name,
       n.file_path AS file_path,
       n.node_type AS node_type,
       'module_level_mutable_variable' AS reason
ORDER BY n.file_path
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
