"""Copies repo-root README/LICENSE into backend/ before every build.

Hatchling rejects a `../` readme/license path, and sdist packaging never
dereferences symlinks (they'd extract as dangling links), so the real
files must exist inside backend/ before hatchling reads them. Without
this hook, `pip install ./backend` from a fresh checkout fails with
"Readme file does not exist" unless scripts/prepare_package_files.sh is
run manually first.
"""

import shutil
from pathlib import Path

from hatchling.metadata.plugin.interface import MetadataHookInterface


class PreparePackageFilesHook(MetadataHookInterface):
    """Runs during metadata read, before hatchling validates readme/license
    paths — a build hook (initialize) fires too late for that validation."""

    def update(self, metadata):
        root = Path(self.root)
        for name in ("README.md", "LICENSE"):
            shutil.copy(root.parent / name, root / name)
