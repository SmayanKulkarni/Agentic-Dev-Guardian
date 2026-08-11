# Spec: Embedded Backing Stores (Drop Docker/Memgraph-Server/Qdrant-Server)

## Problem Statement

`dev-guardian serve` (the MCP entry point) requires Memgraph (Bolt,
`127.0.0.1:7687`) and Qdrant (HTTP, `127.0.0.1:6333`) to be reachable before
any graph or vector operation works. Both currently only ship as Docker
containers, started by a separate `dev-guardian init` step
(`core/infra.py`). If Docker Desktop isn't running, or `init` was never run,
the MCP connection fails outright (`Connection closed`, or every graph/vector
tool call raises `InfraError`). For a single-user local dev tool, requiring a
container runtime and a manual bootstrap step just to answer "what calls
this function?" is disproportionate to the problem, and Docker Desktop
staying resident the whole time an editor is open is unwanted background
load.

## Solution

Replace both server-backed stores with embedded, in-process equivalents that
start the instant `dev-guardian serve` runs — no daemon, no `init` step, no
Docker dependency at all.

1. **Graph store**: Memgraph (Bolt server, driven via `gqlalchemy`) → **Kùzu**
   (embedded, file-based, openCypher-compatible graph DB, pure Python
   package, no server process). Kùzu supports the same Cypher constructs
   already in use, including variable-length relationship patterns
   (`[:CALLS*1..3]`), so `memgraph_client.py`'s query bodies port with
   minimal rewriting.
2. **Vector store**: Qdrant server (HTTP, `qdrant-client` in remote mode) →
   **Qdrant embedded mode** (`QdrantClient(path=...)`, same official
   `qdrant-client` package, same API surface, local-file persistence instead
   of a server connection). This is a constructor-argument change, not a
   library change.
3. **Data location**: per-project, under `.guardian/` inside the indexed
   repository (e.g. `.guardian/kuzu/`, `.guardian/qdrant/`), matching the
   existing convention that the indexed repo is a per-invocation argument,
   not global state. Added to `.gitignore`.
4. **Remove the server-mode path entirely**: delete `core/infra.py` (Docker
   probe/bootstrap/teardown), the `dev-guardian init` / `dev-guardian down`
   CLI commands, and `backend/docker-compose.yml`. No opt-in remote/shared
   mode is kept — this is a single-user local tool and the added
   host/port configuration surface isn't earning its keep.

## User Stories

1. As a developer, I want `dev-guardian serve` to work the first time I
   launch it against a new repo, so that I never have to run a separate
   `init` command or think about container state.
2. As a developer, I want to close my laptop lid and reopen it without
   Guardian's backing services needing to be relaunched, so that using the
   MCP doesn't depend on background daemons surviving sleep/wake.
3. As a developer without Docker installed, I want Guardian to work anyway,
   so that the tool doesn't gate itself on infrastructure unrelated to the
   actual code-analysis feature.
4. As a developer, I want each project's graph/vector index stored inside
   that project's own directory, so that indexes for unrelated repos never
   mix and deleting a repo cleans up its index too.
5. As a developer who already has an indexed repo, I want to understand that
   this change requires re-indexing (old Memgraph/Qdrant Docker volumes are
   not migrated), so I'm not surprised when a stale volume has data the new
   embedded stores don't see.
6. As a maintainer, I want `memgraph_client.py`'s Cypher query bodies reused
   almost as-is in the new `kuzu_client.py`, so that the ABAC clearance
   filtering and impact-analysis logic isn't silently altered during the
   swap.
7. As a maintainer, I want the Docker-specific code path deleted rather than
   kept as a dead fallback, so that there's exactly one way backing storage
   works and no unused code drifting out of sync.

## Implementation Decisions

- **`graphrag/kuzu_client.py`** (new, replaces `graphrag/memgraph_client.py`):
  same public method surface — `ensure_schema()` (renamed from
  `ensure_indexes()`, see below), `ingest_parse_result`, `query_node_by_name`,
  `query_impact_analysis`, `execute_query`, `clear_graph`. Constructor takes
  a `data_dir: Path` instead of `host`/`port`, and opens
  `kuzu.Database(str(data_dir / "kuzu"))` + `kuzu.Connection(db)`.
- **Schema**: Kùzu requires explicit node/relationship table declarations
  before MERGE will work (unlike Memgraph's schemaless property graph).
  `ensure_schema()` issues `CREATE NODE TABLE IF NOT EXISTS ASTNode(name
  STRING, file_path STRING, node_type STRING, start_line INT64, end_line
  INT64, docstring STRING, owner_team STRING, clearance_level INT64,
  PRIMARY KEY(name, file_path))` (composite key mirrors the existing
  `MERGE (n:ASTNode {name: $name, file_path: $file_path})` uniqueness) plus
  one `CREATE REL TABLE IF NOT EXISTS <TYPE>(FROM ASTNode TO ASTNode,
  file_path STRING)` per `EdgeType` value used in `_upsert_edge`. This
  replaces the four `CREATE INDEX ON :ASTNode(...)` statements — Kùzu
  primary keys are indexed automatically, so no separate index step is
  needed for `name`/`file_path`; keep secondary lookups (by
  `clearance_level`, `node_type`) unindexed unless profiling later shows a
  need (YAGNI).
- **Query bodies**: `_upsert_node`, `_upsert_edge`, `_resolve_target_path`,
  `query_node_by_name`, `query_impact_analysis`, `execute_query`,
  `clear_graph` keep their Cypher strings essentially unchanged — Kùzu's
  Cypher dialect covers `MERGE`, `MATCH`, `WHERE`, variable-length
  `[:TYPE*1..n]`, and parameterized queries the same way. `execute_query`'s
  row-flattening (`dict(v) if hasattr(v, "_asdict")`) gets adjusted to
  whatever row/node object shape `kuzu.Connection.execute()` returns —
  confirm against the installed `kuzu` version during implementation rather
  than assuming gqlalchemy's node-wrapper shape carries over.
- **`graphrag/qdrant_client.py`**: constructor changes from
  `QdrantClient(host=self._host, port=self._port)` to
  `QdrantClient(path=str(data_dir / "qdrant"))`. Everything else
  (`COLLECTION_NAME`, `VectorParams`, `PointStruct`, `Filter`/`FieldCondition`
  ABAC payload filtering, `fastembed` embedding) is unchanged — same
  library, same methods, only the connection mode differs.
- **`core/config.py`**: remove `memgraph_host`, `memgraph_port`,
  `qdrant_host`, `qdrant_port`. Add a single `data_dir` concept — not a
  global setting, since data location is per-indexed-repo. Both
  `KuzuClient` and `QdrantCodeClient` take the indexed repo path (or a
  `Path` derived from it, `<repo>/.guardian/`) as a constructor argument,
  passed down from wherever the repo path is already threaded through today
  (mirrors how the indexed repository is already "a CLI argument, never
  configuration" per the existing docstring in `config.py`).
- **`.gitignore`**: add `.guardian/` so generated indexes never get
  committed.
- **Deletions**: `core/infra.py`, its test file(s), the `init`/`down`
  subcommands in `cli.py`, `backend/docker-compose.yml`, and the
  `InfraError`/Docker-availability error strings. Any MCP tool or CLI
  command that currently calls `infra.require_ready()` as a precondition
  check is updated to just proceed — the embedded stores are always "ready"
  once the directory exists (created on first use, no readiness race to
  probe).
- **Dependencies** (`backend/pyproject.toml`): remove `gqlalchemy`, add
  `kuzu`. `qdrant-client` and `fastembed` stay.
- **No migration path for existing Docker-volume data**: out of scope, see
  below — this is a from-scratch re-index.

## Testing Decisions

- `kuzu_client.py` gets the same shape of test coverage
  `memgraph_client.py` presumably already has (check existing test file
  before writing new ones) — ingest a small `ParseResult` fixture into a
  temp-directory-backed `KuzuClient`, then assert `query_node_by_name` and
  `query_impact_analysis` return the expected nodes, including the
  ABAC-clearance filter excluding an over-clearance node.
- `qdrant_client.py` tests swap their fixture's client construction from a
  live/mocked server connection to `QdrantClient(path=<tmp_path>)` — real
  embedded Qdrant against a pytest `tmp_path`, no server or mock needed,
  which is a strict simplification of whatever server-mocking existed
  before.
- No test needed for `core/infra.py` — it's deleted, and its tests are
  deleted with it.
- Add one integration-style test that runs `dev-guardian serve` (or the
  underlying startup path) against a fresh temp repo with no pre-existing
  `.guardian/` directory and confirms a graph+vector operation succeeds
  without any external process running — this is the regression test for
  "no daemon required," the actual point of this change.

## Out of Scope

- Any opt-in remote/shared-server mode (a team pointing Guardian at one
  shared Memgraph/Qdrant instance) — deliberately dropped, not deferred;
  re-add only if genuine multi-user demand shows up.
- Migrating data out of existing `guardian-memgraph`/`guardian-qdrant`
  Docker volumes into the new embedded stores — users re-index affected
  repos from scratch (`dev-guardian` re-run against the repo). Existing
  containers can be removed manually (`docker rm -f guardian-memgraph
  guardian-qdrant`); Guardian no longer manages them.
- Performance tuning of Kùzu/embedded-Qdrant for very large repos — first
  cut targets correctness and "just works," not scale.
- Any UI/CLI command to inspect or manage the `.guardian/` directory beyond
  what already exists for the graph/vector operations themselves.

## Further Notes

This spec was produced from a live debugging session: `guardian` MCP failed
to reconnect (`-32000: Connection closed`), traced to `dev-guardian serve`
requiring Memgraph+Qdrant, which required Docker Desktop, which had a dead
daemon. Rather than just fixing the immediate Docker Desktop issue, the user
asked to eliminate the always-on-service requirement entirely, which led to
this redesign.
