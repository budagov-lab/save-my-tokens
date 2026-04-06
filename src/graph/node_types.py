"""Node and edge type definitions for the dependency graph."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class NodeType(str, Enum):
    """Types of nodes in the dependency graph."""

    FILE = "File"
    MODULE = "Module"
    FUNCTION = "Function"
    CLASS = "Class"
    VARIABLE = "Variable"
    TYPE = "Type"
    INTERFACE = "Interface"
    COMMIT = "Commit"


class EdgeType(str, Enum):
    """Types of edges in the dependency graph."""

    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    DEFINES = "DEFINES"
    INHERITS = "INHERITS"
    DEPENDS_ON = "DEPENDS_ON"
    TYPE_OF = "TYPE_OF"
    IMPLEMENTS = "IMPLEMENTS"
    MODIFIED_BY = "MODIFIED_BY"


@dataclass
class Node:
    """Represents a node in the dependency graph."""

    node_id: str
    type: NodeType
    name: str
    file: str
    line: int
    column: int
    docstring: Optional[str] = None
    parent: Optional[str] = None
    metadata: Optional[Dict[str, str]] = None

    def to_cypher_props(self) -> Dict[str, Any]:
        """Convert node to Neo4j node properties."""
        props = {
            "node_id": self.node_id,
            "name": self.name,
            "type": self.type.value,
            "file": self.file,
            "line": self.line,
            "column": self.column,
        }
        if self.docstring:
            props["docstring"] = self.docstring
        if self.parent:
            props["parent"] = self.parent
        if self.metadata:
            props.update(self.metadata)
        return props


@dataclass
class Edge:
    """Represents an edge in the dependency graph."""

    source_id: str
    target_id: str
    type: EdgeType
    metadata: Optional[Dict[str, Any]] = None

    def to_cypher_props(self) -> Dict[str, Any]:
        """Convert edge to Neo4j edge properties."""
        props = {"type": self.type.value}
        if self.metadata:
            props.update(self.metadata)
        return props


@dataclass
class CommitNode:
    """Represents a git commit in the version graph."""

    commit_hash: str       # Full SHA
    short_hash: str        # First 8 characters
    message: str           # First line of commit message
    author: str            # Commit author name
    timestamp: str         # ISO 8601 timestamp
    branch: str            # Branch name at commit time
    files_changed: int     # Number of files modified

    def to_cypher_props(self) -> Dict[str, Any]:
        """Convert commit to Neo4j node properties."""
        return {
            "node_id": f"Commit:{self.commit_hash}",
            "commit_hash": self.commit_hash,
            "short_hash": self.short_hash,
            "message": self.message,
            "author": self.author,
            "timestamp": self.timestamp,
            "branch": self.branch,
            "files_changed": self.files_changed,
        }
