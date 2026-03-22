"""
Memgraph Cypher Client for AST Knowledge Graph.

Architecture Blueprint Reference: Phase 2 — Memgraph & Qdrant Integration.
This module handles all Cypher query operations against Memgraph:
  - Ingesting ASTNode and ASTEdge objects from Phase 1 as graph entities.
  - Retrieving nodes with mandatory ABAC Fine-Grained Access filtering.
  - Querying structural relationships (e.g., impact analysis).

SECURITY MANDATE: Every retrieval query MUST enforce
  `WHERE node.clearance_level <= $user_clearance`
to respect the proprietary code access control model.
"""

from typing import Optional

from gqlalchemy import Memgraph

from dev_guardian.core.config import get_settings
from dev_guardian.core.logging import get_logger
from dev_guardian.parsers.models import (
    ASTEdge,
    ASTNode,
    EdgeType,
    ParseResult,
)

logger = get_logger(__name__)


class MemgraphClient:
    """
    Cypher-based client for the Memgraph Knowledge Graph.

    Ingests AST Nodes/Edges from Tree-sitter and exposes
    ABAC-filtered retrieval queries.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> None:
        """
        Initialize connection to Memgraph.

        Args:
            host: Memgraph host address (default from config).
            port: Memgraph Bolt port (default from config).
        """
        settings = get_settings()
        self._host = host or settings.memgraph_host
        self._port = port or settings.memgraph_port
        self._db = Memgraph(
            host=self._host,
            port=self._port,
        )
        logger.info(
            "memgraph_client_init",
            host=self._host,
            port=self._port,
        )

    def ensure_indexes(self) -> None:
        """
        Create Memgraph indexes for fast lookups.

        Indexes on :ASTNode(name) and :ASTNode(clearance_level)
        ensure both identifier queries and ABAC filters are fast.
        """
        index_queries = [
            "CREATE INDEX ON :ASTNode(name);",
            "CREATE INDEX ON :ASTNode(clearance_level);",
            "CREATE INDEX ON :ASTNode(file_path);",
            "CREATE INDEX ON :ASTNode(node_type);",
        ]
        for query in index_queries:
            try:
                self._db.execute(query)
            except Exception:
                # Index may already exist
                pass
        logger.info("memgraph_indexes_created")

    def ingest_parse_result(self, result: ParseResult) -> dict[str, int]:
        """
        Ingest a complete ParseResult into Memgraph.

        Creates graph nodes for each ASTNode and edges for
        each ASTEdge from the Phase 1 Tree-sitter output.

        Args:
            result: ParseResult from ASTParser.

        Returns:
            Dictionary with counts of ingested nodes and edges.
        """
        node_count = 0
        edge_count = 0

        for node in result.nodes:
            self._upsert_node(node)
            node_count += 1

        for edge in result.edges:
            self._upsert_edge(edge)
            edge_count += 1

        logger.info(
            "memgraph_ingest_complete",
            nodes=node_count,
            edges=edge_count,
        )
        return {"nodes_ingested": node_count, "edges_ingested": edge_count}

    def _upsert_node(self, node: ASTNode) -> None:
        """
        MERGE an ASTNode into the Knowledge Graph.

        Uses MERGE to avoid duplicates on re-indexing runs.
        ABAC metadata (owner_team, clearance_level) is always set.
        """
        query = """
        MERGE (n:ASTNode {name: $name, file_path: $file_path})
        SET n.node_type = $node_type,
            n.start_line = $start_line,
            n.end_line = $end_line,
            n.docstring = $docstring,
            n.owner_team = $owner_team,
            n.clearance_level = $clearance_level
        """
        self._db.execute(
            query,
            {
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

        If the target node doesn't exist yet (e.g., external import),
        it is created as a stub node with default ABAC clearance.
        """
        source_path = edge.file_path
        target_path = self._resolve_target_path(edge)

        query = f"""
        MERGE (src:ASTNode {{name: $source, file_path: $source_path}})
        ON CREATE SET src.node_type = 'external',
                      src.owner_team = 'unassigned',
                      src.clearance_level = 0
        MERGE (tgt:ASTNode {{name: $target, file_path: $target_path}})
        ON CREATE SET tgt.node_type = 'external',
                      tgt.owner_team = 'unassigned',
                      tgt.clearance_level = 0
        MERGE (src)-[r:{edge.edge_type.value.upper()}]->(tgt)
        SET r.file_path = $file_path
        """
        self._db.execute(
            query,
            {
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
        1. Same file as the edge (for local functions/methods).
        2. Unique global match by name.
        3. Stable unresolved namespace to avoid cross-file node corruption.
        """
        same_file_query = """
        MATCH (t:ASTNode {name: $target, file_path: $file_path})
        RETURN t.file_path AS file_path
        LIMIT 1
        """
        same_file = list(
            self._db.execute_and_fetch(
                same_file_query,
                {
                    "target": edge.target,
                    "file_path": edge.file_path,
                },
            )
        )
        if same_file:
            return str(same_file[0]["file_path"])

        # Imports usually refer to modules, not local symbols.
        if edge.edge_type == EdgeType.IMPORTS:
            return "__module__"

        candidates_query = """
        MATCH (t:ASTNode {name: $target})
        RETURN DISTINCT t.file_path AS file_path
        LIMIT 2
        """
        candidates = list(
            self._db.execute_and_fetch(
                candidates_query,
                {
                    "target": edge.target,
                },
            )
        )
        if len(candidates) == 1:
            return str(candidates[0]["file_path"])

        return "__unresolved__"

    def query_node_by_name(
        self,
        name: str,
        user_clearance: int = 0,
    ) -> list[dict]:
        """
        Retrieve a node by name with ABAC filtering.

        SECURITY: The WHERE clause enforces that the querying
        user can only see nodes at or below their clearance.

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
        results = list(
            self._db.execute_and_fetch(
                query,
                {"name": name, "user_clearance": user_clearance},
            )
        )
        return [dict(r["n"]) for r in results]

    def query_impact_analysis(
        self,
        function_name: str,
        user_clearance: int = 0,
        max_depth: int = 3,
    ) -> list[dict]:
        """
        Find all nodes that directly or transitively depend on
        a given function — "What breaks if I change this?".

        SECURITY: Every node in the traversal path is filtered
        by ABAC clearance.

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
        results = list(
            self._db.execute_and_fetch(
                query,
                {
                    "name": function_name,
                    "user_clearance": user_clearance,
                },
            )
        )
        return [dict(r["impacted"]) for r in results]

    def clear_graph(self) -> None:
        """Delete all nodes and edges. Use for testing only."""
        self._db.execute("MATCH (n) DETACH DELETE n")
        logger.warning("memgraph_graph_cleared")
