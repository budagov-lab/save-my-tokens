"""Parse git diffs to identify symbol-level changes."""

import re
from dataclasses import dataclass
from typing import List, Optional, Set

from loguru import logger


@dataclass
class FileDiff:
    """Represents changes to a single file."""

    file_path: str
    status: str  # "added", "modified", "deleted", "renamed"
    old_path: Optional[str] = None  # For renames
    added_lines: int = 0
    deleted_lines: int = 0


@dataclass
class DiffSummary:
    """Summary of changes across multiple files."""

    files: List[FileDiff]
    total_files_changed: int
    total_lines_added: int
    total_lines_deleted: int


class DiffParser:
    """Parse git diffs to identify file-level changes."""

    # Patterns for parsing git diff headers
    # Example: diff --git a/path/to/file.py b/path/to/file.py
    # Handles filenames with spaces by splitting on " b/" separator
    # (which is reliable: " b/" can't appear in a filename path before the " b/" of the second path)
    DIFF_HEADER_PATTERN = re.compile(
        r"^diff --git a/(.+?) b/(.+)$", re.MULTILINE
    )

    # Pattern for file status in diff: "new file mode", "deleted file mode", etc.
    FILE_STATUS_PATTERN = re.compile(
        r"^(new file mode|deleted file mode|similarity index|rename from|rename to)"
    )

    # Pattern for hunk headers: @@ -10,5 +15,8 @@
    HUNK_PATTERN = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")

    def parse_diff(self, diff_text: str) -> DiffSummary:
        """Parse git diff output and return summary of changes.

        Args:
            diff_text: Raw git diff output

        Returns:
            DiffSummary with file-level changes
        """
        files: List[FileDiff] = []
        total_lines_added = 0
        total_lines_deleted = 0

        # Split by diff headers to get individual file changes
        file_diffs = re.split(r"^diff --git", diff_text, flags=re.MULTILINE)[1:]

        for file_diff in file_diffs:
            lines = file_diff.split("\n")

            # Parse the header line: " a/path/to/file b/path/to/file"
            # Split on " b/" to handle filenames with spaces correctly
            header_line = lines[0].strip()
            if not header_line.startswith("a/"):
                continue

            # Find the " b/" separator (indicates start of new path)
            b_separator_pos = header_line.rfind(" b/")
            if b_separator_pos == -1:
                continue

            old_path = header_line[2:b_separator_pos]  # Skip "a/" prefix
            new_path = header_line[b_separator_pos + 3:]  # Skip " b/" prefix

            # Determine file status
            status = "modified"
            if any("new file mode" in line for line in lines[:5]):
                status = "added"
                old_path = None
            elif any("deleted file mode" in line for line in lines[:5]):
                status = "deleted"
            elif any("rename from" in line for line in lines[:5]):
                status = "renamed"

            # Count added/deleted lines
            added = 0
            deleted = 0
            for line in lines[1:]:
                if line.startswith("+") and not line.startswith("+++"):
                    added += 1
                elif line.startswith("-") and not line.startswith("---"):
                    deleted += 1

            file_diff = FileDiff(
                file_path=new_path,
                status=status,
                old_path=old_path,
                added_lines=added,
                deleted_lines=deleted,
            )
            files.append(file_diff)
            total_lines_added += added
            total_lines_deleted += deleted

        return DiffSummary(
            files=files,
            total_files_changed=len(files),
            total_lines_added=total_lines_added,
            total_lines_deleted=total_lines_deleted,
        )

    def identify_changed_files(self, diff_summary: DiffSummary) -> Set[str]:
        """Identify only .py/.ts files that changed.

        Args:
            diff_summary: Summary from parse_diff

        Returns:
            Set of file paths that changed and should be re-parsed
        """
        supported_extensions = {".py", ".ts", ".tsx", ".js", ".jsx"}
        changed_files = set()

        for file_diff in diff_summary.files:
            # Skip deleted files (they're already gone)
            if file_diff.status == "deleted":
                continue

            # Check if it's a supported file type
            for ext in supported_extensions:
                if file_diff.file_path.endswith(ext):
                    changed_files.add(file_diff.file_path)
                    break

        logger.info(
            f"Identified {len(changed_files)} files to re-parse "
            f"(out of {len(diff_summary.files)} changed)"
        )
        return changed_files

    def is_structural_change(
        self,
        file_path: str,
        before_symbols: Optional[List[str]] = None,
        after_symbols: Optional[List[str]] = None,
    ) -> bool:
        """Determine if a file's AST structure changed.

        A structural change means the list of top-level symbols
        (functions, classes) changed.

        Args:
            file_path: Path to file (for logging)
            before_symbols: List of symbol names before change
            after_symbols: List of symbol names after change

        Returns:
            True if structure changed, False if only content changed
        """
        if before_symbols is None or after_symbols is None:
            # If we don't have symbol info, assume it's a structural change
            return True

        before_set = set(before_symbols)
        after_set = set(after_symbols)

        # Check if any symbols were added or removed
        if before_set != after_set:
            logger.info(
                f"Structural change detected in {file_path}: "
                f"added={after_set - before_set}, "
                f"removed={before_set - after_set}"
            )
            return True

        logger.debug(f"No structural change in {file_path} (same symbols)")
        return False
