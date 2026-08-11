"""
KuzuClient against a real embedded database in tmp_path — no server, no mocks.

These pin the behaviours the Memgraph client was carrying: MERGE-based
idempotent ingest, name lookup, transitive impact analysis, and the ABAC
clearance filter that must exclude over-clearance nodes.
"""
from __future__ import annotations

import pytest

from dev_guardian.graphrag.kuzu_client import KuzuClient
from dev_guardian.parsers.models import (
    ASTEdge,
    ASTNode,
    EdgeType,
    NodeType,
    ParseResult,
)


def _node(name: str, clearance: int = 0, file_path: str = "/repo/app.py") -> ASTNode:
    return ASTNode(
        name=name,
        node_type=NodeType.FUNCTION,
        file_path=file_path,
        start_line=1,
        end_line=5,
        docstring=f"docs for {name}",
        owner_team="core",
        clearance_level=clearance,
    )


@pytest.fixture()
def client(tmp_path) -> KuzuClient:
    return KuzuClient(data_dir=tmp_path)


@pytest.fixture()
def sample_result() -> ParseResult:
    """calculate_tax <- charge_customer <- checkout, plus a secret caller."""
    nodes = [
        _node("calculate_tax"),
        _node("charge_customer"),
        _node("checkout"),
        _node("secret_batch_job", clearance=5),
    ]
    edges = [
        ASTEdge(
            source="charge_customer",
            target="calculate_tax",
            edge_type=EdgeType.CALLS,
            file_path="/repo/app.py",
        ),
        ASTEdge(
            source="checkout",
            target="charge_customer",
            edge_type=EdgeType.CALLS,
            file_path="/repo/app.py",
        ),
        ASTEdge(
            source="secret_batch_job",
            target="calculate_tax",
            edge_type=EdgeType.CALLS,
            file_path="/repo/app.py",
        ),
    ]
    return ParseResult(nodes=nodes, edges=edges, total_files=1)


def test_ingest_reports_counts(client, sample_result):
    stats = client.ingest_parse_result(sample_result)

    assert stats == {"nodes_ingested": 4, "edges_ingested": 3}


def test_query_node_by_name_returns_properties(client, sample_result):
    client.ingest_parse_result(sample_result)

    rows = client.query_node_by_name("calculate_tax", user_clearance=0)

    assert len(rows) == 1
    assert rows[0]["name"] == "calculate_tax"
    assert rows[0]["file_path"] == "/repo/app.py"
    assert rows[0]["node_type"] == "function"
    assert "_id" not in rows[0]


def test_query_node_by_name_hides_over_clearance_nodes(client, sample_result):
    client.ingest_parse_result(sample_result)

    assert client.query_node_by_name("secret_batch_job", user_clearance=0) == []
    assert len(client.query_node_by_name("secret_batch_job", user_clearance=5)) == 1


def test_impact_analysis_is_transitive(client, sample_result):
    client.ingest_parse_result(sample_result)

    impacted = {
        row["name"]
        for row in client.query_impact_analysis("calculate_tax", user_clearance=0)
    }

    assert impacted == {"charge_customer", "checkout"}


def test_impact_analysis_excludes_over_clearance_callers(client, sample_result):
    client.ingest_parse_result(sample_result)

    at_zero = {
        r["name"] for r in client.query_impact_analysis("calculate_tax", user_clearance=0)
    }
    at_five = {
        r["name"] for r in client.query_impact_analysis("calculate_tax", user_clearance=5)
    }

    assert "secret_batch_job" not in at_zero
    assert "secret_batch_job" in at_five


def test_reingest_is_idempotent(client, sample_result):
    client.ingest_parse_result(sample_result)
    client.ingest_parse_result(sample_result)

    assert len(client.query_node_by_name("calculate_tax", user_clearance=0)) == 1


def test_same_name_in_two_files_stays_distinct(client):
    client.ingest_parse_result(
        ParseResult(
            nodes=[
                _node("helper", file_path="/repo/a.py"),
                _node("helper", file_path="/repo/b.py"),
            ],
            edges=[],
            total_files=2,
        )
    )

    rows = client.query_node_by_name("helper", user_clearance=0)

    assert {r["file_path"] for r in rows} == {"/repo/a.py", "/repo/b.py"}


def test_execute_query_returns_named_columns(client, sample_result):
    client.ingest_parse_result(sample_result)

    rows = client.execute_query(
        "MATCH (n:ASTNode) WHERE n.clearance_level <= $cl "
        "RETURN n.name AS name ORDER BY name",
        {"cl": 0},
    )

    assert [r["name"] for r in rows] == [
        "calculate_tax",
        "charge_customer",
        "checkout",
    ]


def test_execute_query_works_on_an_empty_store(client):
    """A never-indexed repo must answer queries, not crash on a missing table."""
    assert client.execute_query("MATCH (n:ASTNode) RETURN n.name AS name") == []


def test_clear_graph_empties_the_store(client, sample_result):
    client.ingest_parse_result(sample_result)

    client.clear_graph()

    assert client.query_node_by_name("calculate_tax", user_clearance=0) == []


def test_nested_sessions_reuse_one_connection(client):
    with client.session() as outer:
        with client.session() as inner:
            assert inner is outer


def test_session_releases_the_lock_on_exit(client, sample_result, tmp_path):
    """A second client on the same directory must work once the first is done."""
    client.ingest_parse_result(sample_result)

    second = KuzuClient(data_dir=tmp_path)

    assert len(second.query_node_by_name("calculate_tax", user_clearance=0)) == 1


def test_call_graph_edge_query_runs_on_kuzu(client):
    """The wiki's call-graph query must not use startNode/endNode (no such
    function in Kùzu) — it walks a zero-or-more prefix then one concrete hop."""
    from dev_guardian.parsers.models import ASTEdge, EdgeType, ParseResult

    client.ingest_parse_result(
        ParseResult(
            nodes=[_node("a"), _node("b"), _node("c")],
            edges=[
                ASTEdge(
                    source="a", target="b",
                    edge_type=EdgeType.CALLS, file_path="/repo/app.py",
                ),
                ASTEdge(
                    source="b", target="c",
                    edge_type=EdgeType.CALLS, file_path="/repo/app.py",
                ),
            ],
            total_files=1,
        )
    )

    rows = client.execute_query(
        """
        MATCH (root:ASTNode)-[:CALLS*0..1]->(caller:ASTNode)-[:CALLS]->(callee:ASTNode)
        WHERE root.name = $fn
          AND root.clearance_level <= $cl
          AND callee.clearance_level <= $cl
        RETURN DISTINCT caller.name AS caller, callee.name AS callee
        LIMIT 80
        """,
        {"fn": "a", "cl": 0},
    )

    assert {(r["caller"], r["callee"]) for r in rows} == {("a", "b"), ("b", "c")}
