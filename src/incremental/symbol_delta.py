"""Symbol delta representation for incremental updates."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List

from src.parsers.symbol import Symbol


@dataclass
class SymbolDelta:
    """Represents changes to symbols in a file."""

    file: str
    added: List[Symbol] = field(default_factory=list)  # New symbols
    deleted: List[str] = field(default_factory=list)  # Symbol names removed
    modified: List[Symbol] = field(default_factory=list)  # Changed definitions
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __repr__(self) -> str:
        """String representation for logging."""
        return (
            f"SymbolDelta(file={self.file}, "
            f"added={len(self.added)}, "
            f"deleted={len(self.deleted)}, "
            f"modified={len(self.modified)})"
        )

    def is_empty(self) -> bool:
        """Check if delta represents no changes."""
        return not self.added and not self.deleted and not self.modified


@dataclass
class UpdateResult:
    """Result of applying a symbol delta."""

    success: bool
    delta: SymbolDelta
    error: str = ""
    duration_ms: float = 0.0

    def __repr__(self) -> str:
        """String representation for logging."""
        status = "✓" if self.success else "✗"
        return (
            f"UpdateResult({status} {self.delta}, "
            f"duration={self.duration_ms:.1f}ms, "
            f"error={self.error if not self.success else 'none'})"
        )
