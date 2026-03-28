"""
PatternTranslator Agent — Natural Language to Memgraph Cypher.

Architecture Blueprint Reference: Phase 5.1 Enhancement — Text-to-Cypher.

This is the FIRST node in the Refactor LangGraph pipeline.
It translates arbitrary natural language refactoring intents into
deterministic Memgraph Cypher queries against the Guardian AST schema.

Decision logic (in order):
  1. If ``pattern`` matches a key in the MIGRATION_PATTERNS registry →
     use the pre-registered Cypher (fast, zero LLM cost, guaranteed correct).
  2. If ``cypher_query`` is already set in state (caller provided raw Cypher) →
     pass through unchanged.
  3. Otherwise → call Groq with the Guardian AST schema to synthesise a query.

This guarantees downstream nodes ALWAYS have a  ``cypher_query`` to execute,
regardless of whether the user typed a pattern key or free-form English.
"""

from __future__ import annotations

from groq import Groq
from langfuse import observe

from dev_guardian.agents.refactor_patterns import MIGRATION_PATTERNS, get_pattern
from dev_guardian.agents.state import RefactorState
from dev_guardian.core.config import get_settings
from dev_guardian.core.logging import get_logger

logger = get_logger(__name__)

# ── Guardian AST Schema injected into every Text-to-Cypher prompt ───
# This gives Groq the exact vocabulary of our Memgraph graph so it
# cannot hallucinate property names or node labels.
GUARDIAN_AST_SCHEMA = """\
## Guardian Memgraph AST Schema

### Node Label
All AST entities are stored as: (:ASTNode)

### Node Properties
| Property       | Type    | Description                                             |
|----------------|---------|---------------------------------------------------------|
| name           | string  | Identifier name (function, class, variable name)        |
| file_path      | string  | Absolute path of the source file                        |
| node_type      | string  | 'function' | 'class' | 'variable' | 'import'           |
| decorators     | string  | Comma-separated decorator names (e.g. "validator,route")|
| bases          | string  | Comma-separated base class names (e.g. "BaseModel")     |
| docstring      | string  | Raw docstring text, or empty string if absent           |
| return_type    | string  | Annotated return type, or empty string if unannotated   |
| scope          | string  | 'module' | 'class' | 'function'                         |
| is_mutable     | boolean | True for mutable module-level variables                 |
| clearance_level| integer | ABAC clearance (0 = public)                             |

### Relationship Types
| Relationship    | Meaning                                          |
|-----------------|--------------------------------------------------|
| [:CALLS]        | source function calls target function            |
| [:IMPORTS]      | source module imports a name from target module  |
| [:INHERITS_FROM]| source class inherits from target class          |
| [:CONTAINS]     | source class or module contains target entity    |

### Query Rules (MANDATORY)
1. ALWAYS return exactly these 4 columns:
   RETURN n.name AS name, n.file_path AS file_path,
          n.node_type AS node_type, '<reason_slug>' AS reason
2. Use MATCH ... WHERE patterns, not shorthand property filters in MATCH.
3. Never use OPTIONAL MATCH — we want definitive hits only.
4. Do NOT include LIMIT — the planner will handle result set size.
5. Output ONLY the raw Cypher query. No explanation, no markdown fences.
"""

TRANSLATOR_SYSTEM_PROMPT = f"""\
You are the Pattern Translator for the Guardian codebase governance system.
Your job is to convert a natural language refactoring intent into a precise
Memgraph Cypher query that targets the Guardian AST graph.

{GUARDIAN_AST_SCHEMA}

## Instructions
1. Analyse the user's intent carefully.
2. Write a Cypher query that finds ALL AST nodes relevant to that intent.
3. Follow all Query Rules above exactly.
4. Return ONLY the raw Cypher — no prose, no code fences.
"""


@observe(name="pattern_translator_agent")
def pattern_translator_node(state: RefactorState) -> dict:
    """
    LangGraph node: Translate a pattern to a Memgraph Cypher query.

    Decision tree:
      - Pre-registered key   → return pre-built Cypher (no LLM).
      - Cypher already set   → pass through (advanced user override).
      - Free text            → call Groq to generate Cypher.

    Writes ``cypher_query`` and ``pattern_description`` to state.

    Args:
        state: Current LangGraph RefactorState.

    Returns:
        Partial state update with cypher_query, pattern_description, messages.
    """
    pattern = state.get("pattern", "").strip()
    existing_cypher = state.get("cypher_query", "").strip()

    # ── Fast path 1: raw Cypher already provided ────────────────
    if existing_cypher:
        logger.info("pattern_translator_passthrough", reason="cypher_already_set")
        return {
            "pattern_description": pattern or "Custom Cypher query",
            "messages": ["[PatternTranslator] Custom Cypher query provided — skipping translation."],
        }

    # ── Fast path 2: pre-registered pattern key ─────────────────
    registered = get_pattern(pattern)
    if registered:
        logger.info("pattern_translator_registered", pattern=pattern)
        return {
            "cypher_query": registered["cypher"].strip(),
            "pattern_description": registered["description"],
            "messages": [
                f"[PatternTranslator] Matched registered pattern '{pattern}' "
                f"— using pre-built Cypher (no LLM cost)."
            ],
        }

    # ── Slow path: free-form natural language → Groq Text-to-Cypher
    if not pattern:
        available = list(MIGRATION_PATTERNS.keys())
        return {
            "cypher_query": "",
            "pattern_description": "",
            "messages": [
                f"[PatternTranslator] No pattern provided. "
                f"Use a natural language intent or one of: {available}"
            ],
        }

    logger.info("pattern_translator_llm", pattern=pattern)

    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": TRANSLATOR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f'Natural language refactoring intent: "{pattern}"\n\n'
                    "Generate the Cypher query to find all relevant AST nodes."
                ),
            },
        ],
        temperature=0.0,   # deterministic output is critical
        max_tokens=512,
    )

    raw_cypher = (response.choices[0].message.content or "").strip()

    # Strip any accidental markdown fences the LLM might add
    raw_cypher = _strip_fences(raw_cypher)

    # Basic sanity check — must contain MATCH and RETURN
    if "MATCH" not in raw_cypher.upper() or "RETURN" not in raw_cypher.upper():
        logger.warning("pattern_translator_bad_cypher", cypher=raw_cypher[:200])
        return {
            "cypher_query": "",
            "pattern_description": pattern,
            "messages": [
                f"[PatternTranslator] LLM generated an invalid Cypher query "
                f"(missing MATCH/RETURN). Raw: {raw_cypher[:200]}"
            ],
        }

    logger.info(
        "pattern_translator_complete",
        cypher_length=len(raw_cypher),
    )

    return {
        "cypher_query": raw_cypher,
        "pattern_description": pattern,
        "messages": [
            f"[PatternTranslator] Translated '{pattern}' → Cypher query "
            f"({len(raw_cypher)} chars)."
        ],
    }


def _strip_fences(text: str) -> str:
    """Remove markdown code fences the LLM may wrap around the Cypher."""
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()
