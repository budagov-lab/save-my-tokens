"""Symbol representation for code analysis."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Symbol:
    """Represents a symbol (function, class, variable, etc.) in source code."""

    name: str
    type: str  # "function", "class", "variable", "import", "type"
    file: str  # Absolute file path
    line: int      # 1-indexed start line
    column: int    # 0-indexed column number
    end_line: Optional[int] = None  # 1-indexed last line of the symbol body
    docstring: Optional[str] = None
    parent: Optional[str] = None  # Qualified name of parent (e.g., "ClassName" for methods)
    node_id: Optional[str] = None  # Unique ID: "type:file:line:name"

    def __post_init__(self):
        """Generate node_id after initialization."""
        if not self.node_id:
            self.node_id = f"{self.type}:{self.file}:{self.line}:{self.name}"

    @property
    def qualified_name(self) -> str:
        """Return fully qualified name (e.g., 'ClassName.method_name')."""
        if self.parent:
            return f"{self.parent}.{self.name}"
        return self.name

    def __hash__(self):
        """Hash based on node_id."""
        return hash(self.node_id)

    def __eq__(self, other):
        """Equality based on node_id."""
        if not isinstance(other, Symbol):
            return False
        return self.node_id == other.node_id

    def __repr__(self):
        """String representation."""
        return f"Symbol({self.type}:{self.qualified_name}@{self.file}:{self.line})"
