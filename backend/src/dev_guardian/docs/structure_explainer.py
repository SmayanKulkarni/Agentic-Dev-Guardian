"""
Structure Explainer — Phase 5.3: Auto-Generating Dynamic Documentation.

Replaces the legacy Mermaid Diagram Generator.
Queries the live Memgraph AST graph and feeds the raw structural edges
(IMPORTS, CALLS, INHERITS_FROM) directly to Groq to generate a concise,
human-readable architectural summary.
"""

from pathlib import Path
from groq import Groq
from dev_guardian.core.logging import get_logger
from dev_guardian.graphrag.memgraph_client import MemgraphClient
from dev_guardian.core.config import get_settings

logger = get_logger(__name__)


def explain_module_dependencies(
    repo_path: Path, mg: MemgraphClient, groq_client: Groq, user_clearance: int = 0
) -> str:
    """
    Generate an AI-narrated summary of inter-module import relationships.
    """
    rows = mg.execute_query(
        """
        MATCH (a:ASTNode)-[:IMPORTS]->(b:ASTNode)
        WHERE a.file_path STARTS WITH $root
          AND a.clearance_level <= $cl
          AND b.clearance_level <= $cl
        RETURN
            a.file_path AS src_file,
            b.file_path AS dst_file
        LIMIT 300
        """,
        {"root": str(repo_path), "cl": user_clearance},
    )

    if not rows:
        return "*No inter-module import relationships were found in the graph.*"

    edges = set()
    for row in rows:
        src = Path(row["src_file"]).stem if row.get("src_file") else "unknown"
        dst = Path(row["dst_file"]).stem if row.get("dst_file") else "unknown"
        if src != dst:
            edges.add((src, dst))

    edge_text = "\n".join([f"- {src} imports {dst}" for src, dst in sorted(edges)])

    prompt = f"""
    You are an expert Software (System Design) Architect analyzing a codebase's module dependencies.
    Below is a raw list of module-level imports extracted from an AST graph:
    
    {edge_text}
    
    Task: Write a single, concise professional paragraph summarizing the high-level architecture of these modules. What are the core dependencies? Which modules act as central hubs? Do not list every single import, just synthesize the structural story.
    """

    settings = get_settings()
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
        )
        explanation = response.choices[0].message.content.strip()
        logger.info("explainer_module_graph_generated", edge_count=len(edges))
        return explanation
    except Exception as e:
        logger.error(f"Failed to generate module explanation: {e}")
        return f"*Error generating architectural explanation: {e}*\n\nRaw Data:\n{edge_text}"


def explain_call_graph(
    function_name: str,
    mg: MemgraphClient,
    groq_client: Groq,
    depth: int = 2,
    user_clearance: int = 0,
) -> str:
    """
    Generate an AI-narrated execution trace of a function.
    """
    rows = mg.execute_query(
        f"""
        MATCH path=(root:ASTNode)-[:CALLS*1..{depth}]->(callee:ASTNode)
        WHERE root.name = $fn
          AND root.clearance_level <= $cl
          AND callee.clearance_level <= $cl
        UNWIND relationships(path) AS rel
        RETURN startNode(rel).name AS caller, endNode(rel).name AS callee
        LIMIT 80
        """,
        {"fn": function_name, "cl": user_clearance},
    )

    if not rows:
        return "*No outgoing execution calls were found in the graph.*"

    edges = set()
    for row in rows:
        caller = row.get("caller", "?")
        callee = row.get("callee", "?")
        if caller and callee:
            edges.add((caller, callee))

    edge_text = "\n".join(
        [f"- `{caller}()` calls `{callee}()`" for caller, callee in sorted(edges)]
    )

    prompt = f"""
    You are an expert Software Architect analyzing a function's execution trace.
    Below is a raw call graph showing what the root function `{function_name}` invokes:
    
    {edge_text}
    
    Task: Write a concise professional paragraph explaining the execution flow of `{function_name}` based on these calls. What subsystems does it trigger? What is its primary structural role? Be brief and technical.
    """

    settings = get_settings()
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
        )
        explanation = response.choices[0].message.content.strip()
        logger.info(
            "explainer_call_graph_generated", fn=function_name, edge_count=len(edges)
        )
        return explanation
    except Exception as e:
        logger.error(f"Failed to generate call graph explanation: {e}")
        return (
            f"*Error generating call graph explanation: {e}*\n\nRaw Data:\n{edge_text}"
        )


def explain_class_hierarchy(
    repo_path: Path, mg: MemgraphClient, groq_client: Groq, user_clearance: int = 0
) -> str:
    """
    Generate an AI-narrated summary of the object-oriented heritage.
    """
    rows = mg.execute_query(
        """
        MATCH (child:ASTNode)-[:INHERITS_FROM]->(parent:ASTNode)
        WHERE child.file_path STARTS WITH $root
          AND child.clearance_level <= $cl
        RETURN child.name AS child, parent.name AS parent
        LIMIT 100
        """,
        {"root": str(repo_path), "cl": user_clearance},
    )

    if not rows:
        return "*No class inheritance relationships were found in the graph.*"

    lines = []
    for row in rows:
        child = row.get("child", "?")
        parent = row.get("parent", "?")
        if child and parent:
            lines.append(f"- Class `{child}` inherits from `{parent}`")

    edge_text = "\n".join(lines)

    prompt = f"""
    You are an expert Software Architect analyzing Object-Oriented Hierarchies.
    Below is a raw list of Python class inheritances found in the repository:
    
    {edge_text}
    
    Task: Write a single concise professional paragraph summarizing this hierarchy. What are the dominant base classes? Are there deep inheritance trees or flat mixins? Evaluate the architectural shape of the OOP design based *only* on this data.
    """

    settings = get_settings()
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
        )
        explanation = response.choices[0].message.content.strip()
        logger.info("explainer_class_hierarchy_generated", row_count=len(rows))
        return explanation
    except Exception as e:
        logger.error(f"Failed to generate class hierarchy explanation: {e}")
        return (
            f"*Error generating hierarchy explanation: {e}*\n\nRaw Data:\n{edge_text}"
        )
