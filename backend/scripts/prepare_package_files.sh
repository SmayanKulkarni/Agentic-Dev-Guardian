#!/usr/bin/env bash
# hatchling rejects a `../` readme/license path, and its sdist packaging
# never dereferences symlinks (they extract as dangling links), so the
# real repo-root files must be copied into backend/ before `python -m build`.
set -euo pipefail
cd "$(dirname "$0")/.."
cp ../README.md README.md
cp ../LICENSE LICENSE
