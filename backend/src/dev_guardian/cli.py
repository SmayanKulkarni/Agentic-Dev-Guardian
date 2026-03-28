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
    skip_vectors: Annotated[
        bool,
        typer.Option(
            "--skip-vectors",
            help="Skip Qdrant vector embedding (saves ~300MB RAM). "
            "Graph-only mode: Memgraph still gets the full AST.",
        ),
    ] = False,
) -> None:
    """Parse code with Tree-sitter and ingest into Memgraph + Qdrant.

    Uses streaming file-by-file ingestion to handle repositories of any
    size without running out of memory. Each file is parsed, ingested,
    then discarded — peak RAM is proportional to a single file, not to
    the entire repository.

    Use --skip-vectors on memory-constrained systems to avoid loading
    the ~270MB ONNX embedding model entirely.
    """
    import gc

    from dev_guardian.parsers.ast_parser import ASTParser
    from dev_guardian.graphrag.vector_manager import predict_embedding_strategy

    logger.info("index_start", path=str(path), language=language)
    typer.echo(f"[bold green]🔍 Indexing codebase:[/bold green] {path}")

    if not skip_vectors:
        strategy = predict_embedding_strategy(path, language)
        if strategy == "lazy":
            typer.echo(
                "[yellow]⚠ Large codebase detected! Automatically switching to "
                "JIT lazy embeddings (--skip-vectors) to prevent OOM.[/yellow]"
            )
            skip_vectors = True
    typer.echo(f"[bold green]🔍 Indexing codebase:[/bold green] {path}")

    parser = ASTParser(language=language)

    # ── Discover files first (cheap — just paths) ──────────────
    pattern = "*.py" if language == "python" else f"*.{language}"
    all_files = sorted(
        f for f in path.rglob(pattern)
        if not parser._should_skip(f)
    )
    total_files = len(all_files)
    typer.echo(f"[cyan]📂 Found {total_files} source files.[/cyan]")

    # ── Init GraphRAG backends ─────────────────────────────────
    from dev_guardian.graphrag.memgraph_client import MemgraphClient

    typer.echo("[cyan]📡 Initializing Memgraph...[/cyan]")
    mg = MemgraphClient()
    mg.ensure_indexes()

    qd = None
    if not skip_vectors:
        typer.echo("[cyan]📡 Initializing Qdrant + ONNX embedder...[/cyan]")
        from dev_guardian.graphrag.qdrant_client import QdrantCodeClient
        qd = QdrantCodeClient()
        qd.ensure_collection()
    else:
        typer.echo("[yellow]⚡ --skip-vectors: Qdrant embedding disabled (saves RAM).[/yellow]")

    # ── Stream: parse one file → ingest → discard ──────────────
    total_nodes = 0
    total_edges = 0
    total_vectors = 0
    file_count = 0

    for i, file_path in enumerate(all_files):
        result = parser.parse_file(file_path)
        if result.total_files == 0:
            continue

        # Ingest nodes into Memgraph (one-by-one Cypher MERGE)
        for node in result.nodes:
            mg._upsert_node(node)
        total_nodes += len(result.nodes)

        # Ingest edges into Memgraph
        for edge in result.edges:
            mg._upsert_edge(edge)
        total_edges += len(result.edges)

        # Embed + upsert nodes into Qdrant (batched internally at 32)
        if qd is not None and result.nodes:
            total_vectors += qd.ingest_nodes(result.nodes)

        file_count += 1

        # Force Python to release this file's objects immediately
        del result
        gc.collect()

        # Progress every 50 files
        if file_count % 50 == 0 or file_count == total_files:
            typer.echo(
                f"  [{file_count}/{total_files}] "
                f"{total_nodes} nodes, {total_edges} edges, "
                f"{total_vectors} vectors"
            )

    typer.echo(
        f"[bold cyan]✅ Indexed {file_count} files — "
        f"{total_nodes} Memgraph Nodes, {total_edges} Memgraph Edges, "
        f"{total_vectors} Qdrant Vectors.[/bold cyan]"
    )
    logger.info(
        "index_complete",
        files=file_count,
        nodes=total_nodes,
        edges=total_edges,
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
    
    # ── JIT Vector Embedding (Phase 5.7) ──────────
    import re
    
    # Extract function/class names added or modified in the diff
    changed_entities = []
    for line in pr_diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            m = re.match(r"^\+\s*(?:def|class)\s+([a-zA-Z0-9_]+)", line)
            if m:
                changed_entities.append(m.group(1))
                
    if changed_entities:
        typer.echo(f"[cyan]🧠 JIT Embedding {len(changed_entities)} detected entities...[/cyan]")
        retriever.jit_embed_nodes(changed_entities, user_clearance=clearance)

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
def audit(
    path: Annotated[
        Path,
        typer.Argument(
            help="Path to the indexed repository root.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    top: Annotated[
        int,
        typer.Option(
            "--top",
            "-n",
            help="Number of highest-risk functions to audit.",
        ),
    ] = 5,
    clearance: Annotated[
        int,
        typer.Option(
            "--clearance",
            "-c",
            help="ABAC clearance level (0=public).",
        ),
    ] = 0,
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Output file for the audit report.",
        ),
    ] = Path("guardian_audit.md"),
) -> None:
    """Proactively audit a codebase for bugs, security issues, and bad patterns.

    Queries Memgraph for the N highest blast-radius functions (most function
    calls = most complex code), reads their actual source from disk, and runs
    them through the full Gatekeeper + Red Team agent pipeline to find real issues.

    Examples:
        guardian audit /path/to/sktime-main
        guardian audit /path/to/sktime-main --top 10
    """
    from dev_guardian.agents.gatekeeper import gatekeeper_node
    from dev_guardian.agents.red_team import redteam_node
    from dev_guardian.agents.state import GuardianState
    from dev_guardian.graphrag.memgraph_client import MemgraphClient

    logger.info("audit_start", path=str(path), top=top)
    typer.echo(f"[bold green]🔍 Guardian Audit:[/bold green] {path}")
    typer.echo(f"[cyan]Scanning top {top} highest-risk functions via Memgraph...[/cyan]\n")

    mg = MemgraphClient()

    # ── Step 1: Find the highest blast-radius functions ──────────
    risky = mg.execute_query(
        """
        MATCH (n:ASTNode)-[:CALLS]->(callee:ASTNode)
        WHERE n.node_type IN ["function", "method"]
          AND n.clearance_level <= $cl
          AND n.file_path STARTS WITH $repo_root
        RETURN n.name as fn, n.file_path as fp,
               n.start_line as sl, n.end_line as el,
               count(callee) as calls
        ORDER BY calls DESC LIMIT $top_n
        """,
        {"cl": clearance, "repo_root": str(path), "top_n": top},
    )

    if not risky:
        typer.echo("[yellow]No high-complexity functions found in the graph. "
                   "Have you run `guardian index` on this path?[/yellow]")
        return

    # ── Step 2: Agents are functions (node-style) ─────────────────
    report_sections: list[str] = [
        f"# 🔍 Guardian Audit Report\n\n"
        f"**Repository**: `{path}`  \n"
        f"**Scanned**: Top {top} highest blast-radius functions  \n\n"
        "---\n"
    ]

    findings: list[dict] = []

    for rank, row in enumerate(risky, 1):
        fn_name = row["fn"]
        fp = row["fp"]
        start_line = row["sl"] or 1
        end_line = row["el"] or start_line + 30
        call_count = row["calls"]
        rel_path = fp.replace(str(path) + "/", "")

        typer.echo(f"  [{rank}/{top}] Auditing `{fn_name}` ({call_count} calls) in {rel_path}")

        # Read source lines
        try:
            src_lines = Path(fp).read_text(encoding="utf-8", errors="replace").splitlines()
            fn_lines = src_lines[max(0, start_line - 1): end_line]
            fn_source = "\n".join(fn_lines)
        except (OSError, IOError) as e:
            typer.echo(f"    [yellow]⚠ Could not read {fp}: {e}[/yellow]")
            continue

        # Wrap as synthetic diff (treat the function as a new addition)
        synthetic_diff = (
            f"--- /dev/null\n"
            f"+++ b/{rel_path}\n"
            f"@@ -0,0 +{start_line},{len(fn_lines)} @@\n"
        ) + "\n".join(f"+{line}" for line in fn_lines)

        from dev_guardian.graphrag.hybrid_retriever import HybridRetriever
        retriever = HybridRetriever()
        
        # ── JIT Vector Embedding (Phase 5.7) ──────────
        retriever.jit_embed_nodes([fn_name], clearance)
        
        # Pull GraphRAG context for the audit
        rag_result = retriever.retrieve(
            query=fn_source[:500], 
            user_clearance=clearance, 
            top_k=5
        )
        context = rag_result.get("merged_context", "")

        # Run Gatekeeper
        state: GuardianState = {
            "pr_diff": synthetic_diff,
            "repo_path": str(path),
            "user_clearance": clearance,
            "graphrag_context": context,
            "messages": [],
        }
        try:
            gk_result = gatekeeper_node(state)
            gk_verdict = gk_result.get("gatekeeper_report", {}).get("verdict", "unknown")
            gk_reason = gk_result.get("gatekeeper_report", {}).get("reasoning", "")
        except Exception as exc:
            gk_verdict = "error"
            gk_reason = str(exc)[:200]

        # Run Red Team
        try:
            rt_result = redteam_node({**state, **gk_result})
            rt_verdict = rt_result.get("redteam_report", {}).get("verdict", "unknown")
            rt_reason = rt_result.get("redteam_report", {}).get("reasoning", "")
        except Exception as exc:
            rt_verdict = "error"
            rt_reason = str(exc)[:200]

        # Severity badge
        if rt_verdict == "fail" or gk_verdict == "fail":
            badge = "🔴 HIGH"
            sev = "high"
        elif rt_verdict == "warn" or gk_verdict == "warn":
            badge = "🟡 MEDIUM"
            sev = "medium"
        else:
            badge = "🟢 PASS"
            sev = "pass"

        icon = {"high": "❌", "medium": "⚠️ ", "pass": "✅"}.get(sev, "?")
        typer.echo(f"    {icon} {badge}  Gatekeeper={gk_verdict}  RedTeam={rt_verdict}")

        findings.append({
            "rank": rank, "name": fn_name, "file": rel_path,
            "calls": call_count, "severity": sev,
            "gk_verdict": gk_verdict, "gk_reason": gk_reason,
            "rt_verdict": rt_verdict, "rt_reason": rt_reason,
        })

        report_sections.append(
            f"## {rank}. `{fn_name}` — {badge}\n\n"
            f"**File**: `{rel_path}` (lines {start_line}–{end_line})  \n"
            f"**Complexity**: {call_count} function calls  \n\n"
            f"### Gatekeeper: `{gk_verdict}`\n{gk_reason[:600]}\n\n"
            f"### Red Team: `{rt_verdict}`\n{rt_reason[:600]}\n\n"
            "---\n"
        )

    # ── Step 3: Write report ──────────────────────────────────────
    high = sum(1 for f in findings if f["severity"] == "high")
    medium = sum(1 for f in findings if f["severity"] == "medium")

    report_sections.insert(
        1,
        f"## Summary\n\n"
        f"| Severity | Count |\n|----------|-------|\n"
        f"| 🔴 High   | {high} |\n"
        f"| 🟡 Medium | {medium} |\n"
        f"| 🟢 Pass   | {len(findings) - high - medium} |\n\n---\n",
    )

    output.write_text("\n".join(report_sections), encoding="utf-8")
    typer.echo("")
    typer.echo(
        f"[bold cyan]✅ Audit complete: {high} high, {medium} medium, "
        f"{len(findings) - high - medium} pass[/bold cyan]"
    )
    typer.echo(f"[bold green]📄 Report written to:[/bold green] {output}")
    logger.info("audit_complete", high=high, medium=medium)


@app.command()
def incident(
    trace: Annotated[
        str,
        typer.Option(
            "--trace",
            "-t",
            help="Raw stack trace string (paste directly from Sentry, stderr, or logs).",
        ),
    ] = "",
    trace_file: Annotated[
        Path,
        typer.Option(
            "--trace-file",
            help="Path to a text file containing the stack trace.",
            exists=False,
        ),
    ] = None,  # type: ignore[assignment]
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            help="Path to the indexed repository root.",
            resolve_path=True,
        ),
    ] = Path("."),
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output path for the generated hotfix blueprint."),
    ] = Path("guardian_hotfix.md"),
    triage_only: Annotated[
        bool,
        typer.Option("--triage-only", help="Only run IncidentTriager (no LLM calls)."),
    ] = False,
) -> None:
    """Triage a production incident and generate a targeted hotfix blueprint.

    Runs the Phase 5.2 SRE Pipeline:
    IncidentTriager (Memgraph) → SandboxReproducer (MoA) → HotfixScribe (Groq).

    Examples:
        guardian incident --trace "Traceback..." --path ./my_repo
        guardian incident --trace-file ./sentry_error.txt --path ./my_repo
        guardian incident --trace "Traceback..." --triage-only
    """
    # ── Resolve stack trace input ───────────────────────────────
    if trace_file is not None and Path(trace_file).exists():
        stack_trace = Path(trace_file).read_text(encoding="utf-8")
    elif trace:
        stack_trace = trace
    else:
        typer.echo(
            "[bold red]Error:[/bold red] Provide --trace or --trace-file.",
            err=True,
        )
        raise typer.Exit(1)

    typer.echo("[bold green]🚨 SRE Incident Response Pipeline[/bold green]")
    typer.echo(f"   Repository: {path}")

    if triage_only:
        # ── Fast path: triage only (no LLM) ────────────────────
        from dev_guardian.agents.incident_triager import incident_triager_node
        result = incident_triager_node(
            {"stack_trace": stack_trace, "repo_path": str(path), "user_clearance": 0, "messages": []}
        )
        ctx = result.get("incident_context", {})
        typer.echo(f"\n[bold]Triage Result:[/bold]")
        typer.echo(f"  Failing function : {ctx.get('failing_function', '?')}")
        typer.echo(f"  File             : {ctx.get('failing_file', '?')}")
        typer.echo(f"  Exception        : {ctx.get('exception_type', '?')}: {ctx.get('exception_msg', '')}")
        typer.echo(f"  Callers at risk  : {ctx.get('caller_count', 0)}")
        return

    # ── Full SRE pipeline ───────────────────────────────────────
    from dev_guardian.agents.sre_graph import build_sre_graph
    graph = build_sre_graph()
    result = graph.invoke(
        {"stack_trace": stack_trace, "repo_path": str(path), "user_clearance": 0, "messages": []}
    )

    blueprint = result.get("hotfix_blueprint", "")
    verdict = result.get("reproduction_verdict", "unknown")
    messages = result.get("messages", [])
    ctx = result.get("incident_context", {})

    typer.echo("\n[bold]Agent Trace:[/bold]")
    for msg in messages:
        typer.echo(f"  {msg}")

    header_lines = [
        "<!-- Guardian SRE Hotfix Blueprint -->",
        f"<!-- Function: {ctx.get('failing_function', '?')} | Reproduction: {verdict} -->",
        "",
    ]
    output.write_text("\n".join(header_lines) + "\n" + blueprint, encoding="utf-8")

    typer.echo(
        f"\n[bold green]✅ Hotfix Blueprint written to:[/bold green] {output} "
        f"(verdict: {verdict})"
    )


@app.command()
def version() -> None:
    """Print the current Agentic Dev Guardian version."""
    typer.echo(f"Agentic Dev Guardian v{__version__}")


@app.command()
def refactor(
    pattern: Annotated[
        str,
        typer.Option(
            "--pattern",
            "-p",
            help=(
                "Migration intent — either a registered key (e.g. 'migrate-pydantic-v1-to-v2') "
                "or any natural language description "
                "(e.g. 'find all functions without docstrings'). "
                "Run without --pattern to list registered keys."
            ),
        ),
    ] = "",
    path: Annotated[
        Path,
        typer.Option(
            "--path",
            help="Path to the indexed repository root.",
            resolve_path=True,
        ),
    ] = Path("."),
    function_name: Annotated[
        str,
        typer.Option("--function", "-f", help="Target function name (for 'deprecate-function' pattern)."),
    ] = "",
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output path for the generated blueprint Markdown."),
    ] = Path("guardian_blueprint.md"),
) -> None:
    """Generate a Self-Healing migration blueprint from a pattern or natural language.

    Accepts either a registered pattern key OR free-form English. Guardian's
    PatternTranslator agent will auto-generate the Memgraph Cypher query for you.

    Examples:
        guardian refactor --pattern migrate-pydantic-v1-to-v2 --path ./my_repo
        guardian refactor --pattern "find all functions without docstrings" --path ./my_repo
        guardian refactor --pattern "migrate all @app.route handlers to FastAPI" --path ./my_repo
    """
    from dev_guardian.agents.refactor_patterns import list_patterns

    if not pattern:
        typer.echo("[bold yellow]Registered refactoring patterns (bypass LLM translation):[/bold yellow]")
        for p in list_patterns():
            typer.echo(f"  ● [cyan]{p['key']}[/cyan]: {p['description']}")
        typer.echo(
            "\n[dim]Tip: You can also pass any natural language intent as --pattern.[/dim]"
        )
        return

    from dev_guardian.agents.refactor_graph import build_refactor_graph

    typer.echo(f"[bold green]🔧 Running Self-Healing Refactor:[/bold green] {pattern}")
    typer.echo(f"   Repository: {path}")

    graph = build_refactor_graph()
    pattern_params = {}
    if function_name:
        pattern_params["function_name"] = function_name

    result = graph.invoke(
        {
            "pattern": pattern,
            "pattern_params": pattern_params,
            "repo_path": str(path),
            "user_clearance": 0,
            "scribe_retry": 0,
            "messages": [],
        }
    )

    blueprint = result.get("blueprint_md", "")
    verdict = result.get("validation_verdict", "unknown")
    messages = result.get("messages", [])
    total_entities = result.get("refactor_plan", {}).get("total_entities", 0)

    # ── Print agent trace ─────────────────────────────────────
    typer.echo("\n[bold]Agent Trace:[/bold]")
    for msg in messages:
        typer.echo(f"  {msg}")

    # ── Write blueprint to file ───────────────────────────────
    header_lines = [
        "<!-- Guardian Self-Healing Blueprint -->",
        f"<!-- Pattern: {pattern} | Entities: {total_entities} | Validation: {verdict} -->",
        "",
    ]
    header = "\n".join(header_lines) + "\n"
    output.write_text(header + blueprint, encoding="utf-8")

    typer.echo(
        f"\n[bold green]✅ Blueprint written to:[/bold green] {output} "
        f"({total_entities} entities, validation: {verdict})"
    )


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

