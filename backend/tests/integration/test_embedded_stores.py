"""
The regression test for the whole point of the embedded-stores change: a repo
that has never been indexed, with no Docker, no daemon and no `init` step,
parses and answers queries.

The graph half runs everywhere (kuzu is a pure package). The vector half is
marked `integration` because the real fastembed model is a ~270MB download.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

from dev_guardian.graphrag.hybrid_retriever import HybridRetriever
from dev_guardian.graphrag.kuzu_client import KuzuClient
from dev_guardian.parsers.ast_parser import ASTParser

SOURCE = '''
def calculate_tax(amount):
    """Compute tax for an amount."""
    return amount * 0.2


def charge_customer(amount):
    """Charge a customer, tax included."""
    return amount + calculate_tax(amount)
'''


@pytest.fixture()
def fresh_repo(tmp_path):
    (tmp_path / "billing.py").write_text(SOURCE, encoding="utf-8")
    assert not (tmp_path / ".guardian").exists()
    return tmp_path


def test_graph_works_on_a_repo_with_no_guardian_directory(fresh_repo):
    parser = ASTParser(language="python")
    result = parser.parse_file(fresh_repo / "billing.py")

    graph = KuzuClient(data_dir=fresh_repo)
    stats = graph.ingest_parse_result(result)

    assert stats["nodes_ingested"] > 0
    assert (fresh_repo / ".guardian" / "kuzu").exists()

    found = graph.query_node_by_name("calculate_tax", user_clearance=0)
    assert found and found[0]["name"] == "calculate_tax"

    impacted = graph.query_impact_analysis("calculate_tax", user_clearance=0)
    assert "charge_customer" in {row["name"] for row in impacted}


def test_query_on_a_never_indexed_repo_returns_empty_not_an_error(tmp_path):
    graph = KuzuClient(data_dir=tmp_path)

    assert graph.query_node_by_name("anything", user_clearance=0) == []


def test_no_external_process_is_required(fresh_repo):
    """Nothing is listening on the old Memgraph/Qdrant ports, by construction.

    This asserts the *code* never dials them: a subprocess with no network
    services running still completes an ingest + query round trip.
    """
    script = (
        "from pathlib import Path;"
        "from dev_guardian.parsers.ast_parser import ASTParser;"
        "from dev_guardian.graphrag.kuzu_client import KuzuClient;"
        f"repo = Path({str(fresh_repo)!r});"
        "r = ASTParser(language='python').parse_file(repo / 'billing.py');"
        "g = KuzuClient(data_dir=repo);"
        "g.ingest_parse_result(r);"
        "print(len(g.query_node_by_name('calculate_tax', 0)))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().endswith("1")


@pytest.mark.integration
def test_hybrid_retrieval_works_end_to_end(fresh_repo):
    """Graph + vectors together, with the real embedding model."""
    parser = ASTParser(language="python")
    result = parser.parse_file(fresh_repo / "billing.py")

    retriever = HybridRetriever(data_dir=fresh_repo)
    summary = retriever.ingest(result)

    assert summary["graph_nodes"] > 0
    assert summary["vectors_embedded"] > 0
    assert (fresh_repo / ".guardian" / "qdrant").exists()

    context = retriever.retrieve("tax calculation", user_clearance=0, top_k=3)

    assert "calculate_tax" in context["merged_context"]
