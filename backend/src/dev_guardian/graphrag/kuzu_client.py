"""
Kùzu Cypher client for the AST Knowledge Graph.

Replaces the Memgraph/Bolt client: Kùzu is embedded and file-backed, so there
is no server, no port and no bootstrap step. The query bodies are carried over
from `memgraph_client.py` — the ABAC clearance filtering and impact-analysis
semantics are meant to be identical.

Two things genuinely differ from Memgraph and shape this module:

  * Kùzu is schema-first. Node and relationship tables must exist before MERGE
    works, and reading an undeclared property is an error rather than NULL.
    `_ensure_schema` runs on every connection open (the statements are
    `IF NOT EXISTS` and cheap) so a never-indexed repo answers queries instead
    of failing on a missing table.
  * Kùzu allows exactly one primary-key column, so node identity is the
    synthetic `id` = "<file_path>::<name>" rather than the composite
    (name, file_path) MERGE key Memgraph used. `name` and `file_path` remain
    ordinary properties, so every query that filtered on them still reads the
    same.

The database is opened per operation and closed after, because the lock is
exclusive across processes: an IDE holding `dev-guardian serve` open would
otherwise block `dev-guardian index` forever. Batch callers hold one outer
`session()` so a bulk ingest still pays a single open.

SECURITY MANDATE: every retrieval query keeps
`WHERE node.clearance_level <= $user_clearance`.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import kuzu

from dev_guardian.core.logging import get_logger
from dev_guardian.core.storage import busy_store, guardian_data_dir
from dev_guardian.parsers.models import (
    ASTEdge,
    ASTNode,
    EdgeType,
    ParseResult,
)

logger = get_logger(__name__)

# One relationship table per edge type the parser can emit. Cheap to declare
# up front, and a query naming a table that does not exist is a hard error.
_REL_TABLES = tuple(edge_type.value.upper() for edge_type in EdgeType)

_NODE_TABLE_DDL = """
CREATE NODE TABLE IF NOT EXISTS ASTNode(
    id STRING,
    name STRING,
    file_path STRING,
    node_type STRING,
    start_line INT64,
    end_line INT64,
    docstring STRING,
    owner_team STRING,
    clearance_level INT64,
    PRIMARY KEY(id)
)
"""


def _node_id(name: str, file_path: str) -> str:
    """The single-column primary key standing in for (name, file_path)."""
    return f"{file_path}::{name}"


def _clean(value: Any) -> Any:
    """Drop Kùzu's internal `_id`/`_label`/`_src`/`_dst` keys from node rows."""
    if isinstance(value, dict) and ("_label" in value or "_id" in value):
        return {k: v for k, v in value.items() if not k.startswith("_")}
    return value


def _rows(result: kuzu.QueryResult) -> list[dict]:
    """QueryResult → list of column-name-keyed dicts."""
    columns = result.get_column_names()
    out: list[dict] = []
    while result.has_next():
        values = result.get_next()
        out.append(
            {col: _clean(val) for col, val in zip(columns, values, strict=False)}
        )
    return out


class KuzuClient:
    """Embedded graph client for the AST Knowledge Graph."""

    def __init__(self, data_dir: Path | str | None = None) -> None:
        """
        Args:
            data_dir: The indexed repository root. The graph lives in
                `<data_dir>/.guardian/kuzu`. Defaults to $GUARDIAN_REPO, then
                the current working directory.
        """
        self.data_dir = guardian_data_dir(data_dir) / "kuzu"
        self._path = str(self.data_dir)
        self._conn: kuzu.Connection | None = None
        logger.info("kuzu_client_init", path=self._path)

    @contextmanager
    def session(self) -> Iterator[kuzu.Connection]:
        """An open connection, reusing the caller's if one is already open.

        The outermost `session()` opens the database and closes it on exit,
        releasing the cross-process lock. Nested calls borrow it.
        """
        if self._conn is not None:
            yield self._conn
            return

        with busy_store(self._path):
            db = kuzu.Database(self._path)
        conn = kuzu.Connection(db)
        self._ensure_schema(conn)
        self._conn = conn
        try:
            yield conn
        finally:
            self._conn = None
            db.close()

    @staticmethod
    def _ensure_schema(conn: kuzu.Connection) -> None:
        """Declare the node and relationship tables. Idempotent."""
        conn.execute(_NODE_TABLE_DDL)
        for table in _REL_TABLES:
            conn.execute(
                f"CREATE REL TABLE IF NOT EXISTS {table}"
                "(FROM ASTNode TO ASTNode, file_path STRING)"
            )

    def ensure_schema(self) -> None:
        """Create the graph schema if it does not exist yet."""
        with self.session():
            pass
        logger.info("kuzu_schema_ready", path=self._path)

    def ingest_parse_result(self, result: ParseResult) -> dict[str, int]:
        """
        Ingest a complete ParseResult.

        Args:
            result: ParseResult from ASTParser.

        Returns:
            Dictionary with counts of ingested nodes and edges.
        """
        node_count = 0
        edge_count = 0

        with self.session():
            for node in result.nodes:
                self._upsert_node(node)
                node_count += 1
            for edge in result.edges:
                self._upsert_edge(edge)
                edge_count += 1

        logger.info("kuzu_ingest_complete", nodes=node_count, edges=edge_count)
        return {"nodes_ingested": node_count, "edges_ingested": edge_count}

    def _upsert_node(self, node: ASTNode) -> None:
        """MERGE an ASTNode. Idempotent across re-indexing runs."""
        query = """
        MERGE (n:ASTNode {id: $id})
        SET n.name = $name,
            n.file_path = $file_path,
            n.node_type = $node_type,
            n.start_line = $start_line,
            n.end_line = $end_line,
            n.docstring = $docstring,
            n.owner_team = $owner_team,
            n.clearance_level = $clearance_level
        """
        with self.session() as conn:
            conn.execute(
                query,
                {
                    "id": _node_id(node.name, node.file_path),
                    "name": node.name,
                    "file_path": node.file_path,
                    "node_type": node.node_type.value,
                    "start_line": node.start_line,
                    "end_line": node.end_line,
                    "docstring": node.docstring or "",
                    "owner_team": node.owner_team,
                    "clearance_level": node.clearance_level,
                },
            )

    def _upsert_edge(self, edge: ASTEdge) -> None:
        """
        MERGE a structural relationship between two ASTNodes.

        A target that does not exist yet (an external import, say) is created
        as a stub with default clearance.
        """
        source_path = edge.file_path
        target_path = self._resolve_target_path(edge)

        query = f"""
        MERGE (src:ASTNode {{id: $source_id}})
        ON CREATE SET src.name = $source,
                      src.file_path = $source_path,
                      src.node_type = 'external',
                      src.owner_team = 'unassigned',
                      src.clearance_level = 0
        MERGE (tgt:ASTNode {{id: $target_id}})
        ON CREATE SET tgt.name = $target,
                      tgt.file_path = $target_path,
                      tgt.node_type = 'external',
                      tgt.owner_team = 'unassigned',
                      tgt.clearance_level = 0
        MERGE (src)-[r:{edge.edge_type.value.upper()}]->(tgt)
        SET r.file_path = $file_path
        """
        with self.session() as conn:
            conn.execute(
                query,
                {
                    "source_id": _node_id(edge.source, source_path),
                    "target_id": _node_id(edge.target, target_path),
                    "source": edge.source,
                    "target": edge.target,
                    "source_path": source_path,
                    "target_path": target_path,
                    "file_path": edge.file_path,
                },
            )

    def _resolve_target_path(self, edge: ASTEdge) -> str:
        """
        Resolve the best target file_path for an edge target name.

        Priority:
        1. Same file as the edge (local functions/methods).
        2. Unique global match by name.
        3. A stable unresolved namespace, so unrelated files never merge.
        """
        same_file_query = """
        MATCH (t:ASTNode {name: $target, file_path: $file_path})
        RETURN t.file_path AS file_path
        LIMIT 1
        """
        with self.session() as conn:
            same_file = _rows(
                conn.execute(
                    same_file_query,
                    {"target": edge.target, "file_path": edge.file_path},
                )
            )
            if same_file:
                return str(same_file[0]["file_path"])

            if edge.edge_type == EdgeType.IMPORTS:
                return "__module__"

            candidates_query = """
            MATCH (t:ASTNode {name: $target})
            RETURN DISTINCT t.file_path AS file_path
            LIMIT 2
            """
            candidates = _rows(
                conn.execute(candidates_query, {"target": edge.target})
            )
        if len(candidates) == 1:
            return str(candidates[0]["file_path"])
        return "__unresolved__"

    def query_node_by_name(self, name: str, user_clearance: int = 0) -> list[dict]:
        """
        Retrieve nodes by name with ABAC filtering.

        SECURITY: the WHERE clause keeps a caller to nodes at or below their
        clearance.

        Args:
            name: Name of the AST entity to find.
            user_clearance: The caller's ABAC clearance level.

        Returns:
            List of matching node property dictionaries.
        """
        query = """
        MATCH (n:ASTNode {name: $name})
        WHERE n.clearance_level <= $user_clearance
        RETURN n
        """
        with self.session() as conn:
            rows = _rows(
                conn.execute(query, {"name": name, "user_clearance": user_clearance})
            )
        return [row["n"] for row in rows]

    def query_impact_analysis(
        self,
        function_name: str,
        user_clearance: int = 0,
        max_depth: int = 3,
    ) -> list[dict]:
        """
        Find everything that directly or transitively calls `function_name` —
        "what breaks if I change this?".

        SECURITY: both ends of the traversal are clearance-filtered.

        Args:
            function_name: The root function to analyze.
            user_clearance: The caller's ABAC clearance level.
            max_depth: Maximum graph traversal depth.

        Returns:
            List of impacted node property dictionaries.
        """
        query = f"""
        MATCH (root:ASTNode {{name: $name}})<-[:CALLS*1..{max_depth}]-(caller:ASTNode)
        WHERE root.clearance_level <= $user_clearance
          AND caller.clearance_level <= $user_clearance
        RETURN DISTINCT caller AS impacted
        """
        with self.session() as conn:
            rows = _rows(
                conn.execute(
                    query,
                    {"name": function_name, "user_clearance": user_clearance},
                )
            )
        return [row["impacted"] for row in rows]

    def execute_query(self, cypher: str, params: dict | None = None) -> list[dict]:
        """
        Execute arbitrary Cypher and return all rows as dicts.

        Used by the migration-pattern queries, which run custom Cypher
        templates against the graph.

        Args:
            cypher: Cypher query string.
            params: Optional parameter dict.

        Returns:
            List of row dicts keyed by column name.
        """
        with self.session() as conn:
            rows = _rows(conn.execute(cypher, params or {}))
        logger.info("execute_query_complete", rows=len(rows))
        return rows

    def clear_graph(self) -> None:
        """Delete all nodes and edges. Use for testing only."""
        with self.session() as conn:
            conn.execute("MATCH (n) DETACH DELETE n")
        logger.warning("kuzu_graph_cleared")
