"""Load and evaluate .smtignore patterns.

Format (subset of .gitignore syntax):
    # comment lines are ignored
    blank lines are ignored
    node_modules          simple name — matches any path component
    tests/fixtures        path pattern — matched against the relative path from project root
    *.generated.py        fnmatch glob — matched against the filename only
    tests/**              path glob — matched against relative path (fnmatch)
"""

import fnmatch
from pathlib import Path
from typing import List


class SMTIgnore:
    """Evaluates .smtignore rules against file paths."""

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self._simple: List[str] = []    # patterns with no '/' — match any path part or filename
        self._path: List[str] = []      # patterns with '/' — match relative path from root

        ignore_file = self.project_root / ".smtignore"
        if ignore_file.exists():
            for raw in ignore_file.read_text(encoding="utf-8").splitlines():
                pattern = raw.strip()
                if not pattern or pattern.startswith("#"):
                    continue
                pattern = pattern.rstrip("/")  # normalise trailing slash
                if "/" in pattern:
                    self._path.append(pattern)
                else:
                    self._simple.append(pattern)

    def is_ignored(self, file_path: Path) -> bool:
        """Return True if file_path should be excluded from graph operations."""
        abs_path = file_path.resolve()

        # --- simple patterns: match any path component or the filename ---
        if self._simple:
            for part in abs_path.parts:
                for pat in self._simple:
                    if fnmatch.fnmatch(part, pat):
                        return True

        # --- path patterns: match relative path from project root ---
        if self._path:
            try:
                rel = abs_path.relative_to(self.project_root)
            except ValueError:
                rel = abs_path  # outside project root — keep as-is
            rel_str = rel.as_posix()
            for pat in self._path:
                if fnmatch.fnmatch(rel_str, pat) or fnmatch.fnmatch(rel_str, pat + "/*"):
                    return True

        return False

    def __bool__(self) -> bool:
        """True if any patterns are loaded."""
        return bool(self._simple or self._path)
