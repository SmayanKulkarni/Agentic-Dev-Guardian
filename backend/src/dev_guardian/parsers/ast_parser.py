"""
Tree-sitter AST Parser Engine.

Architecture Blueprint Reference: Phase 1 — Core Python Package & AST Parsers.
This module wraps Tree-sitter to deterministically extract AST Nodes
(Functions, Classes) and Edges (CALLS, IMPORTS, INHERITS_FROM) from
Python source files.

IMPORTANT: This parser uses pure mathematical AST traversal. We NEVER
send raw proprietary code to an external LLM to build the graph.
This is the "Data Minimization Edge" defined in the Security Guardrails.
"""

from pathlib import Path
from typing import Optional

import tree_sitter_python as tspython
from tree_sitter import Language, Parser, Node

from dev_guardian.core.logging import get_logger
from dev_guardian.parsers.models import (
    ASTEdge,
    ASTNode,
    EdgeType,
    NodeType,
    ParseResult,
)

logger = get_logger(__name__)

PY_LANGUAGE = Language(tspython.language())


class ASTParser:
    """
    Deterministic AST parser using Tree-sitter.

    This class traverses Abstract Syntax Trees to identify structural
    entities (Nodes) and their relationships (Edges) with 100% accuracy.
    No LLM inference is used here — purely mathematical parsing.
    """

    def __init__(self, language: str = "python") -> None:
        """
        Initialize the parser for a given language.

        Args:
            language: Programming language to parse (currently 'python').
        """
        self.language = language
        self.parser = Parser(PY_LANGUAGE)
        logger.info("ast_parser_init", language=language)

    def parse_file(self, file_path: Path) -> ParseResult:
        """
        Parse a single source file and extract all AST Nodes and Edges.

        Args:
            file_path: Absolute path to the Python source file.

        Returns:
            ParseResult containing all extracted Nodes and Edges.
        """
        try:
            source_code = file_path.read_bytes()
        except (OSError, IOError) as e:
            logger.error("file_read_error", path=str(file_path), error=str(e))
            return ParseResult()

        tree = self.parser.parse(source_code)
        root = tree.root_node

        nodes: list[ASTNode] = []
        edges: list[ASTEdge] = []

        self._extract_nodes(root, str(file_path), nodes, edges)

        return ParseResult(
            total_files=1,
            total_nodes=len(nodes),
            total_edges=len(edges),
            nodes=nodes,
            edges=edges,
        )

    def parse_directory(self, directory: Path) -> ParseResult:
        """
        Recursively parse all Python files in a directory.

        Args:
            directory: Path to the codebase root directory.

        Returns:
            Aggregated ParseResult across all files.
        """
        all_nodes: list[ASTNode] = []
        all_edges: list[ASTEdge] = []
        file_count = 0

        pattern = "*.py" if self.language == "python" else f"*.{self.language}"

        for file_path in sorted(directory.rglob(pattern)):
            if self._should_skip(file_path):
                continue

            result = self.parse_file(file_path)
            all_nodes.extend(result.nodes)
            all_edges.extend(result.edges)
            file_count += 1

            logger.debug(
                "file_parsed",
                file=str(file_path),
                nodes=result.total_nodes,
                edges=result.total_edges,
            )

        return ParseResult(
            total_files=file_count,
            total_nodes=len(all_nodes),
            total_edges=len(all_edges),
            nodes=all_nodes,
            edges=all_edges,
        )

    def _extract_nodes(
        self,
        node: Node,
        file_path: str,
        nodes: list[ASTNode],
        edges: list[ASTEdge],
        parent_name: Optional[str] = None,
    ) -> None:
        """
        Recursively traverse the AST tree and extract Nodes/Edges.

        Args:
            node: Current Tree-sitter AST node.
            file_path: Path of the source file being parsed.
            nodes: Accumulator list for extracted ASTNode objects.
            edges: Accumulator list for extracted ASTEdge objects.
            parent_name: Name of the parent entity (for CONTAINS edges).
        """
        if node.type == "function_definition":
            func_name = self._get_identifier(node)
            if func_name:
                docstring = self._get_docstring(node)
                nodes.append(
                    ASTNode(
                        name=func_name,
                        node_type=NodeType.METHOD if parent_name else NodeType.FUNCTION,
                        file_path=file_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        docstring=docstring,
                    )
                )
                if parent_name:
                    edges.append(
                        ASTEdge(
                            source=parent_name,
                            target=func_name,
                            edge_type=EdgeType.CONTAINS,
                            file_path=file_path,
                        )
                    )
                # Extract calls only from the body block to avoid infinite recursion
                for child in node.children:
                    if child.type == "block":
                        self._extract_calls(child, func_name, file_path, edges)
                        # Recurse into body to find nested functions
                        for body_child in child.children:
                            self._extract_nodes(
                                body_child, file_path, nodes, edges, func_name
                            )
                return

        elif node.type == "class_definition":
            class_name = self._get_identifier(node)
            if class_name:
                docstring = self._get_docstring(node)
                nodes.append(
                    ASTNode(
                        name=class_name,
                        node_type=NodeType.CLASS,
                        file_path=file_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        docstring=docstring,
                    )
                )
                self._extract_superclasses(node, class_name, file_path, edges)
                # Recurse into class body to find methods
                for child in node.children:
                    self._extract_nodes(child, file_path, nodes, edges, class_name)
                return

        elif node.type == "import_statement" or node.type == "import_from_statement":
            self._extract_imports(node, file_path, edges, parent_name)

        # Default: recurse into children
        for child in node.children:
            self._extract_nodes(child, file_path, nodes, edges, parent_name)

    def _get_identifier(self, node: Node) -> Optional[str]:
        """Extract the name identifier from a function/class definition node."""
        for child in node.children:
            if child.type == "identifier":
                return child.text.decode("utf-8") if child.text else None
        return None

    def _get_docstring(self, node: Node) -> Optional[str]:
        """Extract the docstring from a function/class body if present."""
        body = None
        for child in node.children:
            if child.type == "block":
                body = child
                break
        if body and body.children:
            first_stmt = body.children[0]
            if first_stmt.type == "expression_statement":
                expr = first_stmt.children[0] if first_stmt.children else None
                if expr and expr.type == "string":
                    text = expr.text.decode("utf-8") if expr.text else None
                    if text:
                        return text.strip("\"'")
        return None

    def _extract_calls(
        self,
        node: Node,
        caller_name: str,
        file_path: str,
        edges: list[ASTEdge],
    ) -> None:
        """Find all function calls within a node and create CALLS edges."""
        if node.type == "call":
            func_node = node.children[0] if node.children else None
            if func_node:
                if func_node.type == "identifier" and func_node.text:
                    callee = func_node.text.decode("utf-8")
                    edges.append(
                        ASTEdge(
                            source=caller_name,
                            target=callee,
                            edge_type=EdgeType.CALLS,
                            file_path=file_path,
                        )
                    )
                elif func_node.type == "attribute" and func_node.text:
                    callee = func_node.text.decode("utf-8")
                    edges.append(
                        ASTEdge(
                            source=caller_name,
                            target=callee,
                            edge_type=EdgeType.CALLS,
                            file_path=file_path,
                        )
                    )

        for child in node.children:
            self._extract_calls(child, caller_name, file_path, edges)

    def _extract_superclasses(
        self,
        node: Node,
        class_name: str,
        file_path: str,
        edges: list[ASTEdge],
    ) -> None:
        """Extract INHERITS_FROM edges from class argument lists."""
        for child in node.children:
            if child.type == "argument_list":
                for arg in child.children:
                    if arg.type == "identifier" and arg.text:
                        parent_class = arg.text.decode("utf-8")
                        edges.append(
                            ASTEdge(
                                source=class_name,
                                target=parent_class,
                                edge_type=EdgeType.INHERITS_FROM,
                                file_path=file_path,
                            )
                        )

    def _extract_imports(
        self,
        node: Node,
        file_path: str,
        edges: list[ASTEdge],
        parent_name: Optional[str] = None,
    ) -> None:
        """Extract IMPORTS edges from import statements."""
        source = parent_name or "__module__"
        if node.text:
            import_text = node.text.decode("utf-8")
            # Extract the module name from the import statement
            parts = import_text.replace("from ", "").replace("import ", "").split()
            if parts:
                target = parts[0]
                edges.append(
                    ASTEdge(
                        source=source,
                        target=target,
                        edge_type=EdgeType.IMPORTS,
                        file_path=file_path,
                    )
                )

    @staticmethod
    def _should_skip(file_path: Path) -> bool:
        """Check if a file should be skipped during parsing."""
        skip_patterns = {
            "__pycache__",
            ".git",
            ".venv",
            "venv",
            "node_modules",
            ".eggs",
            "dist",
            "build",
        }
        return any(part in skip_patterns for part in file_path.parts)
