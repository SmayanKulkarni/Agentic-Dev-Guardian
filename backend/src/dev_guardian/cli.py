"""
Typer CLI Interface for Agentic Dev Guardian.

Architecture Blueprint Reference: Phase 1 — Core Python Package & AST Parsers.
This module exposes the primary `guardian` CLI commands:
    - `guardian index <path>`: Parse a codebase and ingest AST into GraphRAG.
    - `guardian evaluate <path>`: Evaluate a PR diff using GraphRAG + MoA agents.
  - `guardian version`: Print the current package version.
"""

from pathlib import Path

import typer
from typing_extensions import Annotated

from dev_guardian import __version__
from dev_guardian.core.logging import get_logger

app = typer.Typer(
    name="guardian",
    help="AI Developer Governance & Codebase Evaluator — "
    "Autonomously evaluate AI-generated code against proprietary codebases.",
    add_completion=False,
    rich_markup_mode="rich",
)

logger = get_logger(__name__)


@app.command()
def index(
    path: Annotated[
        Path,
        typer.Argument(
            help="Path to the codebase directory to parse and index.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    language: Annotated[
        str,
        typer.Option("--language", "-l", help="Programming language to parse."),
    ] = "python",
) -> None:
    """Parse code with Tree-sitter and ingest into Memgraph + Qdrant."""
    from dev_guardian.parsers.ast_parser import ASTParser

    logger.info("index_start", path=str(path), language=language)
    typer.echo(f"[bold green]🔍 Indexing codebase:[/bold green] {path}")

    parser = ASTParser(language=language)
    results = parser.parse_directory(path)

    typer.echo("[cyan]📡 Ingesting into GraphRAG (Memgraph + Qdrant)...[/cyan]")
    from dev_guardian.graphrag.hybrid_retriever import HybridRetriever
    
    retriever = HybridRetriever()
    summary = retriever.ingest(results)

    typer.echo(
        f"[bold cyan]✅ Indexed {results.total_files} files — "
        f"{summary['graph_nodes']} Memgraph Nodes, {summary['graph_edges']} Memgraph Edges, "
        f"{summary['vectors_embedded']} Qdrant Vectors.[/bold cyan]"
    )
    logger.info(
        "index_complete",
        files=results.total_files,
        nodes=results.total_nodes,
        edges=results.total_edges,
    )


@app.command()
def evaluate(
    diff_file: Annotated[
        Path,
        typer.Argument(
            help="Path to the PR diff file to evaluate.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            resolve_path=True,
        ),
    ],
    repo_path: Annotated[
        Path,
        typer.Option(
            "--repo",
            "-r",
            help="Path to the indexed repository root.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ] = Path("."),
    clearance: Annotated[
        int,
        typer.Option(
            "--clearance",
            "-c",
            help="ABAC clearance level (0=public, higher=restricted).",
        ),
    ] = 0,
) -> None:
    """Evaluate a PR diff with GraphRAG context and the MoA decision pipeline."""
    from dev_guardian.agents.graph import build_guardian_graph
    from dev_guardian.graphrag.hybrid_retriever import HybridRetriever

    logger.info("evaluate_start", diff_file=str(diff_file))
    typer.echo(f"[bold green]🛡️  Evaluating PR diff:[/bold green] {diff_file}")

    # Read the diff
    pr_diff = diff_file.read_text(encoding="utf-8")

    # Retrieve GraphRAG context
    typer.echo("[cyan]📡 Querying GraphRAG (Memgraph + Qdrant)...[/cyan]")
    retriever = HybridRetriever()
    rag_result = retriever.retrieve(
        query=pr_diff[:500],  # use first 500 chars as query
        user_clearance=clearance,
        top_k=10,
    )
    context = rag_result.get("merged_context", "")

    # Build and invoke the graph
    typer.echo("[cyan]🤖 Invoking MoA Agent Pipeline...[/cyan]")
    graph = build_guardian_graph()
    result = graph.invoke(
        {
            "pr_diff": pr_diff,
            "repo_path": str(repo_path),
            "user_clearance": clearance,
            "graphrag_context": context,
            "messages": [],
        }
    )

    # Display results
    decision = result.get("decision", "unknown")
    messages = result.get("messages", [])

    typer.echo("")
    for msg in messages:
        typer.echo(f"  {msg}")
    typer.echo("")

    if decision == "approve":
        typer.echo("[bold green]✅ APPROVED — PR is safe to merge.[/bold green]")
    elif decision in ("remediate", "remediated"):
        typer.echo(
            "[bold yellow]🔧 REMEDIATED — PR had issues. "
            "Suggested fix below:[/bold yellow]"
        )
        fix = result.get("remediation_diff", "")
        if fix:
            typer.echo(f"\n```\n{fix}\n```")
    else:
        typer.echo(f"[bold red]❌ Decision: {decision}[/bold red]")

    logger.info("evaluate_complete", decision=decision)


@app.command()
def version() -> None:
    """Print the current Agentic Dev Guardian version."""
    typer.echo(f"Agentic Dev Guardian v{__version__}")


@app.command()
def serve() -> None:
    """Start the MCP server for IDE integration (stdio transport).

    Launches the Model Context Protocol server that exposes
    Guardian tools (query_guardian_graph, evaluate_pr_diff,
    impact_analysis, index_codebase) to any MCP-compatible IDE
    such as Cursor, Claude Desktop, or Windsurf.

    The server communicates over stdin/stdout using the MCP protocol.
    Configure your IDE's MCP settings to point to this command.
    """
    from dev_guardian.mcp_server import run_server

    typer.echo(
        "[bold cyan]🚀 Starting MCP Server (stdio transport)...[/bold cyan]",
        err=True,
    )
    run_server()


if __name__ == "__main__":
    app()

