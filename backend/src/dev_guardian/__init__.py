"""
Agentic Dev Guardian — AI Developer Governance & Codebase Evaluator.

A GraphRAG-powered multi-agent system that autonomously evaluates, tests,
and governs AI-generated code against proprietary codebases using
deterministic AST parsing (Tree-sitter), semantic vector search (Qdrant),
and structural knowledge graphs (Memgraph).
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

try:
    # Single source of truth: the installed distribution's metadata, which
    # hatch-vcs derives from the git tag. A hardcoded literal here would drift
    # from the wheel on every commit after a tag.
    __version__ = _version("agentic-dev-guardian")
except PackageNotFoundError:  # running from a source tree, not installed
    __version__ = "0.0.0+unknown"
