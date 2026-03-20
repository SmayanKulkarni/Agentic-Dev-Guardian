"""
Pydantic Data Models for AST Nodes and Edges.

Architecture Blueprint Reference: Phase 1 — Core Python Package & AST Parsers.
These models represent the deterministic, mathematical entities extracted
from Tree-sitter AST traversals. They define the strict schema that will
later be injected into Memgraph (Phase 2).

Nodes = Functions, Classes, Variables
Edges = CALLS, INHERITS_FROM, IMPORTS
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    """Types of AST entities that become graph Nodes."""

    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    VARIABLE = "variable"
    MODULE = "module"


class EdgeType(str, Enum):
    """Types of structural relationships that become graph Edges."""

    CALLS = "calls"
    INHERITS_FROM = "inherits_from"
    IMPORTS = "imports"
    CONTAINS = "contains"
    DECORATES = "decorates"


class ASTNode(BaseModel):
    """
    A single AST entity extracted from source code.

    Attributes:
        name: The identifier name (e.g., function name, class name).
        node_type: The category of this entity (function, class, etc.).
        file_path: Absolute path to the source file containing this entity.
        start_line: The line number where this entity's definition begins.
        end_line: The line number where this entity's definition ends.
        docstring: The entity's docstring, if present.
        owner_team: ABAC metadata tag for Fine-Grained Access Control (Phase 2).
        clearance_level: ABAC security clearance (default 0 = public).
    """

    name: str
    node_type: NodeType
    file_path: str
    start_line: int
    end_line: int
    docstring: Optional[str] = None
    owner_team: str = Field(default="unassigned", description="ABAC metadata tag")
    clearance_level: int = Field(default=0, description="ABAC clearance level")


class ASTEdge(BaseModel):
    """
    A structural relationship between two AST Nodes.

    Attributes:
        source: Name of the source Node (caller / parent).
        target: Name of the target Node (callee / child).
        edge_type: The type of relationship (CALLS, INHERITS_FROM, etc.).
        file_path: File where this relationship was detected.
    """

    source: str
    target: str
    edge_type: EdgeType
    file_path: str


class ParseResult(BaseModel):
    """
    Aggregated result of parsing an entire codebase directory.

    Attributes:
        total_files: Number of source files successfully parsed.
        total_nodes: Total AST Nodes (functions, classes, etc.) extracted.
        total_edges: Total AST Edges (calls, imports, etc.) extracted.
        nodes: List of all extracted ASTNode objects.
        edges: List of all extracted ASTEdge objects.
    """

    total_files: int = 0
    total_nodes: int = 0
    total_edges: int = 0
    nodes: list[ASTNode] = Field(default_factory=list)
    edges: list[ASTEdge] = Field(default_factory=list)
