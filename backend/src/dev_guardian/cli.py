"""
Typer CLI Interface for Agentic Dev Guardian.

Architecture Blueprint Reference: Phase 1 — Core Python Package & AST Parsers.
This module exposes the primary `guardian` CLI commands:
  - `guardian index <path>`: Parse a codebase and extract its AST structure.
  - `guardian evaluate <path>`: (Placeholder) Evaluate a PR diff against the graph.
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
    """Parse a codebase directory and extract AST Nodes & Edges using Tree-sitter."""
    from dev_guardian.parsers.ast_parser import ASTParser

    logger.info("index_start", path=str(path), language=language)
    typer.echo(f"[bold green]🔍 Indexing codebase:[/bold green] {path}")

    parser = ASTParser(language=language)
    results = parser.parse_directory(path)

    typer.echo(
        f"[bold cyan]✅ Indexed {results.total_files} files — "
        f"{results.total_nodes} Nodes, {results.total_edges} "
        "Edges extracted.[/bold cyan]"
    )
    logger.info(
        "index_complete",
        files=results.total_files,
        nodes=results.total_nodes,
        edges=results.total_edges,
    )


@app.command()
def evaluate(
    path: Annotated[
        Path,
        typer.Argument(
            help="Path to the PR diff file or directory to evaluate.",
            exists=True,
            resolve_path=True,
        ),
    ],
) -> None:
    """
    Evaluate a PR diff against the codebase Knowledge Graph.
    (Phase 3 placeholder).
    """
    typer.echo(
        "[bold yellow]⚠️  Evaluation engine requires Phase 3 (LangGraph Agents). "
        "Currently a placeholder.[/bold yellow]"
    )
    logger.warning("evaluate_not_implemented")


@app.command()
def version() -> None:
    """Print the current Agentic Dev Guardian version."""
    typer.echo(f"Agentic Dev Guardian v{__version__}")


if __name__ == "__main__":
    app()
