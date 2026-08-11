"""
Typer CLI Interface for Agentic Dev Guardian.

Architecture Blueprint Reference: Phase 1 — Core Python Package & AST Parsers.
This module exposes the primary `dev-guardian` CLI commands:
    - `dev-guardian index <path>`: Parse a codebase and ingest its AST into
      the embedded stores under `<path>/.guardian/`.
    - `dev-guardian evaluate <diff>`: Evaluate a PR diff using GraphRAG + MoA agents.
    - `dev-guardian mcp-config`: Print the config block for your MCP client.
    - `dev-guardian version`: Print the current package version.
"""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from dev_guardian import __version__
from dev_guardian.core.logging import get_logger
from dev_guardian.skills import register_all_skills

register_all_skills()

app = typer.Typer(
    name="dev-guardian",
    help="AI Developer Governance & Codebase Evaluator — "
    "Autonomously evaluate AI-generated code against proprietary codebases.",
    add_completion=False,
    rich_markup_mode="rich",
)

logger = get_logger(__name__)

_stdout = Console()
_stderr = Console(stderr=True)


def _echo(message: str = "", err: bool = False) -> None:
    """Print a line, rendering rich markup.

    `typer.echo` is `click.echo`: it does not interpret `[bold]`-style markup,
    so every tagged string used to reach the user with the tags still in it.
    `rich_markup_mode` only ever applied to `--help` text.
    """
    (_stderr if err else _stdout).print(message)


_MCP_COMMAND = "uvx"
_MCP_ARGS = ["--from", "agentic-dev-guardian", "dev-guardian", "serve"]

# Where each client reads its MCP config, and under which top-level key. The
# shapes genuinely differ: VS Code uses `servers`, Codex uses TOML, everyone
# else settled on Claude Desktop's `mcpServers`.
MCP_CLIENTS: dict[str, str] = {
    "claude": "~/.claude.json, or `claude mcp add-json guardian '<block>'`",
    "cursor": "~/.cursor/mcp.json (or .cursor/mcp.json in the repo)",
    "windsurf": "~/.codeium/windsurf/mcp_config.json",
    "antigravity": "~/.antigravity/mcp_config.json",
    "claude-desktop": "claude_desktop_config.json",
    "vscode": ".vscode/mcp.json (or the user-level mcp.json)",
    "codex": "~/.codex/config.toml",
}


def _mcp_env() -> dict[str, str]:
    """The env block every client shape carries, from the resolved settings."""
    import os

    provider = os.environ.get("GUARDIAN_PROVIDER", "groq")
    key_var = {
        "groq": "GUARDIAN_GROQ_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
    }.get(provider)
    env = {
        "GUARDIAN_PROVIDER": provider,
        # The repository whose `.guardian/` stores Guardian reads. The MCP
        # client spawns the server with no useful cwd, so the repo is named
        # explicitly rather than inferred.
        "GUARDIAN_REPO": str(Path.cwd().resolve()),
    }
    if key_var:
        # Never echo the resolved key: this output gets pasted into chats,
        # issues and screen shares. The user fills it in at paste time.
        env[key_var] = "<your-api-key>"
    model = os.environ.get("GUARDIAN_MODEL")
    if model:
        env["GUARDIAN_MODEL"] = model
    preload = os.environ.get("GUARDIAN_PRELOAD_CLUSTERS")
    if preload:
        env["GUARDIAN_PRELOAD_CLUSTERS"] = preload
    return env


def _mcp_config_json(client: str = "claude") -> str:
    """The MCP client block for this install, in `client`'s own shape.

    Guardian writes no config of its own (ticket 06) — the IDE's `env` block
    is the configuration channel, so `init` just prints what to paste.

    Raises:
        KeyError: `client` is not one of MCP_CLIENTS.
    """
    import json

    if client not in MCP_CLIENTS:
        raise KeyError(client)

    env = _mcp_env()

    if client == "codex":
        # Codex reads TOML, not JSON. json.dumps doubles as a TOML string
        # literal writer here: both use "..." with backslash escapes.
        lines = [
            "[mcp_servers.guardian]",
            f"command = {json.dumps(_MCP_COMMAND)}",
            f"args = [{', '.join(json.dumps(a) for a in _MCP_ARGS)}]",
            "",
            "[mcp_servers.guardian.env]",
            *(f"{k} = {json.dumps(v)}" for k, v in env.items()),
        ]
        return "\n".join(lines)

    server = {"command": _MCP_COMMAND, "args": list(_MCP_ARGS), "env": env}
    if client == "vscode":
        # VS Code keys servers under `servers` and wants the transport named.
        return json.dumps({"servers": {"guardian": {"type": "stdio", **server}}}, indent=2)
    return json.dumps({"mcpServers": {"guardian": server}}, indent=2)


@app.command("mcp-config")
def mcp_config(
    client: Annotated[
        str,
        typer.Option(
            "--client",
            help="Which client to emit config for: " + ", ".join(MCP_CLIENTS),
        ),
    ] = "claude",
) -> None:
    """Print the config block to paste into your MCP client.

    Guardian writes no config of its own — the IDE's `env` block is the
    configuration channel, so this just prints what to paste. `GUARDIAN_REPO`
    is filled in from the current directory, which is the repository the
    server will read `.guardian/` from.
    """
    try:
        block = _mcp_config_json(client)
    except KeyError:
        _echo(
            f"[bold red]Unknown client '{client}'. Expected one of: "
            f"{', '.join(MCP_CLIENTS)}.[/bold red]",
            err=True,
        )
        raise typer.Exit(code=2) from None
    _echo(f"[dim]# paste into {MCP_CLIENTS[client]}[/dim]", err=True)
    print(block)


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
        typer.Option("--language", "-l", help="Source language. Only 'python' is supported today."),
    ] = "python",
    skip_vectors: Annotated[
        bool,
        typer.Option(
            "--skip-vectors",
            help="Skip Qdrant vector embedding (saves ~300MB RAM). "
            "Graph-only mode: Kùzu still gets the full AST.",
        ),
    ] = False,
) -> None:
    """Parse code with Tree-sitter and ingest into the embedded Kùzu + Qdrant stores.

    Uses streaming file-by-file ingestion to handle repositories of any
    size without running out of memory. Each file is parsed, ingested,
    then discarded — peak RAM is proportional to a single file, not to
    the entire repository.

    Use --skip-vectors on memory-constrained systems to avoid loading
    the ~270MB ONNX embedding model entirely.
    """
    import gc

    from dev_guardian.graphrag.vector_manager import predict_embedding_strategy
    from dev_guardian.parsers.ast_parser import ASTParser

    logger.info("index_start", path=str(path), language=language)
    _echo(f"[bold green]🔍 Indexing codebase:[/bold green] {path}")

    if not skip_vectors:
        strategy = predict_embedding_strategy(path, language)
        if strategy == "lazy":
            _echo(
                "[yellow]⚠ Large codebase detected! Automatically switching to "
                "JIT lazy embeddings (--skip-vectors) to prevent OOM.[/yellow]"
            )
            skip_vectors = True

    try:
        parser = ASTParser(language=language)
    except ValueError as exc:
        _echo(f"[red]✗ {exc}[/red]", err=True)
        raise typer.Exit(code=1) from exc

    # ── Discover files first (cheap — just paths) ──────────────
    pattern = "*.py" if language == "python" else f"*.{language}"
    all_files = sorted(
        f for f in path.rglob(pattern)
        if not parser._should_skip(f)
    )
    total_files = len(all_files)
    _echo(f"[cyan]📂 Found {total_files} source files.[/cyan]")

    # ── Init GraphRAG backends ─────────────────────────────────
    from contextlib import ExitStack

    from dev_guardian.graphrag.kuzu_client import KuzuClient

    _echo(f"[cyan]📡 Opening embedded graph store in {path}/.guardian/kuzu...[/cyan]")
    graph = KuzuClient(data_dir=path)

    qd = None
    if not skip_vectors:
        _echo("[cyan]📡 Opening embedded vector store + ONNX embedder...[/cyan]")
        from dev_guardian.graphrag.qdrant_client import QdrantCodeClient
        qd = QdrantCodeClient(data_dir=path)
    else:
        _echo("[yellow]⚡ --skip-vectors: vector embedding disabled (saves RAM).[/yellow]")

    # ── Stream: parse one file → ingest → discard ──────────────
    total_nodes = 0
    total_edges = 0
    total_vectors = 0
    file_count = 0

    # One outer session per store: both embedded engines take an exclusive
    # file lock, and reopening per file would be pure overhead.
    with ExitStack() as stack:
        stack.enter_context(graph.session())
        if qd is not None:
            stack.enter_context(qd.session())
            qd.ensure_collection()

        for file_path in all_files:
            result = parser.parse_file(file_path)
            if result.total_files == 0:
                continue

            for node in result.nodes:
                graph._upsert_node(node)
            total_nodes += len(result.nodes)

            for edge in result.edges:
                graph._upsert_edge(edge)
            total_edges += len(result.edges)

            if qd is not None and result.nodes:
                total_vectors += qd.ingest_nodes(result.nodes)

            file_count += 1

            # Force Python to release this file's objects immediately
            del result
            gc.collect()

            # Progress every 50 files
            if file_count % 50 == 0 or file_count == total_files:
                _echo(
                    f"  [{file_count}/{total_files}] "
                    f"{total_nodes} nodes, {total_edges} edges, "
                    f"{total_vectors} vectors"
                )

    _echo(
        f"[bold cyan]✅ Indexed {file_count} files — "
        f"{total_nodes} graph nodes, {total_edges} graph edges, "
        f"{total_vectors} vectors → {path}/.guardian[/bold cyan]"
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
            help="Graph retrieval scope (higher pulls back more). Not a security boundary.",
        ),
    ] = 0,
) -> None:
    """Evaluate a PR diff with GraphRAG context and the MoA decision pipeline."""
    from dev_guardian.agents.graph import build_guardian_graph
    from dev_guardian.graphrag.hybrid_retriever import HybridRetriever

    logger.info("evaluate_start", diff_file=str(diff_file))
    _echo(f"[bold green]🛡️  Evaluating PR diff:[/bold green] {diff_file}")

    # Read the diff
    pr_diff = diff_file.read_text(encoding="utf-8")

    # Retrieve GraphRAG context
    _echo("[cyan]📡 Querying GraphRAG (Kùzu + Qdrant)...[/cyan]")
    retriever = HybridRetriever(data_dir=repo_path)
    
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
        _echo(f"[cyan]🧠 JIT Embedding {len(changed_entities)} detected entities...[/cyan]")
        retriever.jit_embed_nodes(changed_entities, user_clearance=clearance)

    rag_result = retriever.retrieve(
        query=pr_diff[:500],  # use first 500 chars as query
        user_clearance=clearance,
        top_k=10,
    )
    context = rag_result.get("merged_context", "")

    # Build and invoke the graph
    _echo("[cyan]🤖 Invoking MoA Agent Pipeline...[/cyan]")
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

    _echo("")
    for msg in messages:
        _echo(f"  {msg}")
    _echo("")

    if decision == "approve":
        _echo("[bold green]✅ APPROVED — PR is safe to merge.[/bold green]")
    elif decision in ("remediate", "remediated"):
        _echo(
            "[bold yellow]🔧 REMEDIATED — PR had issues. "
            "Suggested fix below:[/bold yellow]"
        )
        fix = result.get("remediation_diff", "")
        if fix:
            _echo(f"\n```\n{fix}\n```")
    else:
        _echo(f"[bold red]❌ Decision: {decision}[/bold red]")

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
            help="Graph retrieval scope (higher pulls back more).",
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

    Queries Kùzu for the N highest blast-radius functions (most function
    calls = most complex code), reads their actual source from disk, and runs
    them through the full Gatekeeper + Red Team agent pipeline to find real issues.

    Examples:
        dev-guardian audit /path/to/sktime-main
        dev-guardian audit /path/to/sktime-main --top 10
    """
    from dev_guardian.audit import run_audit

    _echo(f"[bold green]🔍 Guardian Audit:[/bold green] {path}")
    _echo(f"[cyan]Scanning top {top} highest-risk functions via Kùzu...[/cyan]\n")

    report = run_audit(
        path=path,
        top=top,
        clearance=clearance,
        on_progress=lambda line: _echo(f"  {line}"),
    )

    if not report.findings:
        _echo(
            "[yellow]No high-complexity functions found in the graph. "
            "Have you run `dev-guardian index` on this path?[/yellow]"
        )
        return

    output.write_text(report.markdown, encoding="utf-8")
    counts = report.counts
    _echo("")
    _echo(
        f"[bold cyan]✅ Audit complete: {counts['high']} high, {counts['medium']} medium, "
        f"{counts['error']} errored, {counts['pass']} pass[/bold cyan]"
    )
    _echo(f"[bold green]📄 Report written to:[/bold green] {output}")


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
    IncidentTriager (Kùzu) → SandboxReproducer (MoA) → HotfixScribe (Groq).

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
        _echo(
            "[bold red]Error:[/bold red] Provide --trace or --trace-file.",
            err=True,
        )
        raise typer.Exit(1)

    _echo("[bold green]🚨 SRE Incident Response Pipeline[/bold green]")
    _echo(f"   Repository: {path}")

    if triage_only:
        # ── Fast path: triage only (no LLM) ────────────────────
        from dev_guardian.agents.incident_triager import incident_triager_node
        result = incident_triager_node(
            {"stack_trace": stack_trace, "repo_path": str(path), "user_clearance": 0, "messages": []}
        )
        ctx = result.get("incident_context", {})
        _echo("\n[bold]Triage Result:[/bold]")
        _echo(f"  Failing function : {ctx.get('failing_function', '?')}")
        _echo(f"  File             : {ctx.get('failing_file', '?')}")
        _echo(f"  Exception        : {ctx.get('exception_type', '?')}: {ctx.get('exception_msg', '')}")
        _echo(f"  Callers at risk  : {ctx.get('caller_count', 0)}")
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

    _echo("\n[bold]Agent Trace:[/bold]")
    for msg in messages:
        _echo(f"  {msg}")

    header_lines = [
        "<!-- Guardian SRE Hotfix Blueprint -->",
        f"<!-- Function: {ctx.get('failing_function', '?')} | Reproduction: {verdict} -->",
        "",
    ]
    output.write_text("\n".join(header_lines) + "\n" + blueprint, encoding="utf-8")

    _echo(
        f"\n[bold green]✅ Hotfix Blueprint written to:[/bold green] {output} "
        f"(verdict: {verdict})"
    )


@app.command()
def version() -> None:
    """Print the current Agentic Dev Guardian version."""
    _echo(f"Agentic Dev Guardian v{__version__}")


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
    PatternTranslator agent will auto-generate the Kùzu Cypher query for you.

    Examples:
        guardian refactor --pattern migrate-pydantic-v1-to-v2 --path ./my_repo
        guardian refactor --pattern "find all functions without docstrings" --path ./my_repo
        guardian refactor --pattern "migrate all @app.route handlers to FastAPI" --path ./my_repo
    """
    from dev_guardian.agents.refactor_patterns import list_patterns

    if not pattern:
        _echo("[bold yellow]Registered refactoring patterns (bypass LLM translation):[/bold yellow]")
        for p in list_patterns():
            _echo(f"  ● [cyan]{p['key']}[/cyan]: {p['description']}")
        _echo(
            "\n[dim]Tip: You can also pass any natural language intent as --pattern.[/dim]"
        )
        return

    from dev_guardian.agents.refactor_graph import build_refactor_graph

    _echo(f"[bold green]🔧 Running Self-Healing Refactor:[/bold green] {pattern}")
    _echo(f"   Repository: {path}")

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
    _echo("\n[bold]Agent Trace:[/bold]")
    for msg in messages:
        _echo(f"  {msg}")

    # ── Write blueprint to file ───────────────────────────────
    header_lines = [
        "<!-- Guardian Self-Healing Blueprint -->",
        f"<!-- Pattern: {pattern} | Entities: {total_entities} | Validation: {verdict} -->",
        "",
    ]
    header = "\n".join(header_lines) + "\n"
    output.write_text(header + blueprint, encoding="utf-8")

    _echo(
        f"\n[bold green]✅ Blueprint written to:[/bold green] {output} "
        f"({total_entities} entities, validation: {verdict})"
    )


@app.command()
def serve(
    transport: Annotated[
        str,
        typer.Option(
            "--transport",
            help="'stdio' for an IDE-spawned subprocess, or 'streamable-http' "
            "to listen on a socket for one or more connecting clients.",
        ),
    ] = "stdio",
    host: Annotated[
        str,
        typer.Option("--host", help="Bind address for --transport streamable-http."),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", help="Bind port for --transport streamable-http."),
    ] = 8000,
    repo: Annotated[
        Path,
        typer.Option(
            "--repo",
            help="Repository whose .guardian/ stores this server reads. "
            "Defaults to $GUARDIAN_REPO, then the current directory.",
            resolve_path=True,
        ),
    ] = None,  # type: ignore[assignment]
) -> None:
    """Start the MCP server for IDE integration.

    Launches the Model Context Protocol server that exposes Guardian's
    bootstrap tools (query_guardian_graph, list_capabilities,
    equip_capability, unequip_capability) to any MCP-compatible IDE such
    as Cursor, Claude Desktop, or Windsurf. Everything else loads JIT.

    Under the default stdio transport the server talks over stdin/stdout
    and your IDE spawns it — run `dev-guardian mcp-config` for the JSON
    block to paste. The graph and vector stores are embedded, so nothing
    needs to be running first; an unindexed repository simply answers with
    no results.

    `--transport streamable-http` serves the same tools over HTTP instead,
    for running one Guardian on the machine that holds the indexed
    codebase. It has no authentication of its own, so it binds to
    127.0.0.1 unless you put it behind a proxy that authenticates.
    """
    valid = {"stdio", "streamable-http", "sse"}
    if transport not in valid:
        _echo(
            f"[bold red]Unknown transport '{transport}'. "
            f"Expected one of: {', '.join(sorted(valid))}.[/bold red]",
            err=True,
        )
        raise typer.Exit(code=2)

    import os

    if repo is not None:
        os.environ["GUARDIAN_REPO"] = str(repo)

    from dev_guardian.mcp_server import run_server

    where = "stdio" if transport == "stdio" else f"{transport} on {host}:{port}"
    _echo(f"[bold cyan]🚀 Starting MCP Server ({where})...[/bold cyan]", err=True)
    run_server(transport=transport, host=host, port=port)


@app.command()
def docs(
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
            help="Number of highest-complexity functions to generate ADRs for.",
        ),
    ] = 5,
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Output file for the generated wiki (default: GUARDIAN_WIKI.md).",
        ),
    ] = Path("GUARDIAN_WIKI.md"),
    clearance: Annotated[
        int,
        typer.Option("--clearance", "-c", help="Graph retrieval scope."),
    ] = 0,
) -> None:
    """Generate a live architecture wiki from the indexed Kùzu graph.

    Phase 5.3: Auto-Generating Dynamic Documentation.

    Queries the already-indexed Kùzu AST graph (no re-parsing needed)
    to produce a comprehensive markdown wiki containing:
      - Module dependency flowchart (Mermaid)
      - Class inheritance hierarchy (Mermaid)
      - Top-N function call graphs (Mermaid)
      - AI-narrated Architectural Decision Records (ADRs)

    All diagrams are derived from IMPORTS / CALLS / INHERITS_FROM edges.
    ADR narration uses the configured LLM provider (GUARDIAN_PROVIDER).
    """
    from dev_guardian.docs.wiki_builder import build_wiki, save_wiki
    from dev_guardian.graphrag.kuzu_client import KuzuClient

    logger.info("docs_start", path=str(path), top=top)
    _echo(f"[bold green]📖 Guardian Docs:[/bold green] {path}")
    _echo(f"[cyan]Generating wiki for top {top} highest-complexity functions...[/cyan]")

    graph = KuzuClient(data_dir=path)

    _echo("[cyan]📡 Querying Kùzu for module graph...[/cyan]")
    wiki_content = build_wiki(
        repo_path=path,
        graph=graph,
        top_n=top,
        user_clearance=clearance,
    )

    wiki_path = save_wiki(wiki_content, output)
    _echo(f"\n[bold green]✅ Wiki written to:[/bold green] {wiki_path}")
    logger.info("docs_complete", output=str(wiki_path))


@app.command("docs-status")
def docs_status(
    path: Annotated[
        Path,
        typer.Argument(
            help="Path to the repository root.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    wiki: Annotated[
        Path,
        typer.Option(
            "--wiki",
            "-w",
            help="Path to the generated wiki (default: GUARDIAN_WIKI.md).",
        ),
    ] = Path("GUARDIAN_WIKI.md"),
) -> None:
    """Check whether GUARDIAN_WIKI.md is stale relative to the repo's HEAD.

    Exits 0 when the wiki's embedded commit matches HEAD, non-zero when it
    is behind. Composable as a CI gate step (`dev-guardian docs-status .`).
    """
    from dev_guardian.docs.staleness import StalenessCheckError, check_staleness

    wiki_path = wiki if wiki.is_absolute() else path / wiki

    try:
        result = check_staleness(path, wiki_path)
    except StalenessCheckError as exc:
        _echo(f"[bold red]❌ {exc}[/bold red]", err=True)
        raise typer.Exit(code=1) from exc

    if not result.stale:
        _echo(
            f"[bold green]✅ Docs are fresh[/bold green] "
            f"(HEAD {result.head_sha[:8]} matches recorded commit)."
        )
        return

    _echo(
        f"[bold red]❌ Docs are stale:[/bold red] {result.commits_behind} commit(s) behind.\n"
        f"  recorded: {result.recorded_sha}\n"
        f"  HEAD:     {result.head_sha}\n"
        f"  Fix: run `dev-guardian docs {path}` and commit the updated wiki.",
        err=True,
    )
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
