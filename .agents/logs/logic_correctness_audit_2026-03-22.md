# Logic & Correctness Audit Fix Log

Timestamp: 2026-03-22T14:31:59+05:30
Scope: backend/src/dev_guardian

## Issue Register (Concise)

1. Non-deterministic Qdrant point IDs caused duplicate vectors across re-indexes.
2. Memgraph edge upsert merged nodes by name only, risking cross-file symbol corruption.
3. Impact analysis traversed all edge types, producing false positives.
4. Supervisor routing sent WARN+FAIL to debate instead of remediation.
5. Parser accepted arbitrary language values but always used Python grammar.
6. Parsed-file count incremented even on file read failures.
7. Import extraction was string-split based and incorrect for multi-import/alias syntax.
8. Remediation parser only stripped specific code-fence language tags.
9. Gatekeeper/Red Team parser had redundant DETAILS parsing code.
10. CLI docs did not describe actual side effects/behavior.

## Fix Log (Why + How)

1. Deterministic vector identity
- Why fixed: repeated indexing must upsert existing vectors, not create duplicates.
- How fixed: replaced Python hash() with stable SHA-256 based 63-bit ID generator in qdrant client.
- File: backend/src/dev_guardian/graphrag/qdrant_client.py

2. Safer edge identity resolution
- Why fixed: name-only MERGE can attach edges to wrong symbols across files.
- How fixed: source nodes now MERGE by name+file_path; target path is resolved by same-file first, unique global fallback, then stable unresolved namespace.
- File: backend/src/dev_guardian/graphrag/memgraph_client.py

3. Impact traversal constrained to calls
- Why fixed: impact analysis should model executable dependency blast radius, not all structural relation types.
- How fixed: Cypher traversal changed from wildcard edges to CALLS-only variable-length traversal.
- File: backend/src/dev_guardian/graphrag/memgraph_client.py

4. WARN+FAIL policy correctness
- Why fixed: intended policy is immediate remediation for warn/fail combinations.
- How fixed: supervisor routing checks WARN+FAIL before generic disagreement route.
- File: backend/src/dev_guardian/agents/graph.py

5. Explicit language support contract
- Why fixed: silently accepting non-python language values produced incorrect behavior.
- How fixed: AST parser now normalizes language and raises ValueError for unsupported languages.
- File: backend/src/dev_guardian/parsers/ast_parser.py

6. Accurate parse metrics
- Why fixed: file_count should reflect successful file parses only.
- How fixed: increment file_count only when parse_file reports total_files == 1.
- File: backend/src/dev_guardian/parsers/ast_parser.py

7. Correct import extraction semantics
- Why fixed: split/replace parsing corrupted import targets and lost multi-import accuracy.
- How fixed: parser now handles "from X import ..." and "import a, b as c" forms explicitly and emits one edge per module target.
- File: backend/src/dev_guardian/parsers/ast_parser.py

8. Robust remediation code-block parsing
- Why fixed: LLM output language tags vary (python, py, python3, etc.).
- How fixed: code-fence language line is stripped using a regex matcher rather than hardcoded tag checks.
- File: backend/src/dev_guardian/agents/remediation.py

9. Redundant parser cleanup
- Why fixed: duplicate DETAILS parsing path was dead/redundant logic.
- How fixed: removed redundant DETAILS branch in loop and kept full DETAILS section extraction.
- Files: backend/src/dev_guardian/agents/gatekeeper.py, backend/src/dev_guardian/agents/red_team.py

10. CLI behavior documentation alignment
- Why fixed: docs implied parse-only behavior while command performs ingestion and MoA evaluation.
- How fixed: updated module and command docstrings to match real runtime behavior.
- File: backend/src/dev_guardian/cli.py

## Validation

- Static diagnostics run: no errors in backend/src/dev_guardian.
