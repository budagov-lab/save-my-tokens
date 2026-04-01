"""Data models for function contracts."""

import ast
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from src.parsers.symbol import Symbol


@dataclass
class ParameterInfo:
    """Information about a function parameter."""

    name: str
    type_hint: Optional[str] = None
    is_optional: bool = False
    default_value: Optional[str] = None
    description: Optional[str] = None


@dataclass
class SignatureInfo:
    """Information about a function signature."""

    parameters: List[ParameterInfo] = field(default_factory=list)
    return_type: Optional[str] = None
    return_description: Optional[str] = None
    raises: List[str] = field(default_factory=list)  # Exception types

    @property
    def param_names(self) -> List[str]:
        """Get parameter names."""
        return [p.name for p in self.parameters]

    @property
    def required_params(self) -> List[str]:
        """Get required (non-optional) parameter names."""
        return [p.name for p in self.parameters if not p.is_optional]

    @property
    def optional_params(self) -> List[str]:
        """Get optional parameter names."""
        return [p.name for p in self.parameters if p.is_optional]


@dataclass
class FunctionContract:
    """Complete contract for a function."""

    symbol: Symbol
    signature: SignatureInfo
    docstring: Optional[str] = None
    type_hints: Dict[str, str] = field(default_factory=dict)  # param -> type
    preconditions: List[str] = field(default_factory=list)  # "requires X", "assumes Y"
    postconditions: List[str] = field(default_factory=list)  # "returns X where..."
    version: str = "1.0"  # Contract version for tracking changes
    timestamp: Optional[str] = None

    def __repr__(self) -> str:
        """String representation."""
        params = ", ".join(self.signature.param_names)
        return f"Contract({self.symbol.name}({params}) -> {self.signature.return_type})"


@dataclass
class BreakingChange:
    """Represents a breaking change between two contracts."""

    type: str  # PARAMETER_REMOVED, RETURN_TYPE_NARROWED, etc.
    severity: str  # HIGH, MEDIUM, LOW
    impact: str  # Human-readable explanation
    affected_elements: Set[str] = field(default_factory=set)  # param/return/exception names
    old_value: Optional[str] = None  # Old value (for comparison)
    new_value: Optional[str] = None  # New value (for comparison)

    def __repr__(self) -> str:
        """String representation."""
        return f"BreakingChange({self.type}[{self.severity}]: {self.impact})"


@dataclass
class ContractComparison:
    """Result of comparing two contracts."""

    old_contract: FunctionContract
    new_contract: FunctionContract
    breaking_changes: List[BreakingChange] = field(default_factory=list)
    non_breaking_changes: List[str] = field(default_factory=list)
    is_compatible: bool = True
    compatibility_score: float = 1.0  # 0-1, where 1.0 is fully compatible

    def __repr__(self) -> str:
        """String representation."""
        breaking = len(self.breaking_changes)
        non_breaking = len(self.non_breaking_changes)
        return (
            f"ContractComparison({self.old_contract.symbol.name}: "
            f"breaking={breaking}, non_breaking={non_breaking}, "
            f"compatible={self.is_compatible})"
        )


class BreakingChangeType:
    """Constants for breaking change types."""

    PARAMETER_REMOVED = "PARAMETER_REMOVED"
    PARAMETER_TYPE_CHANGED = "PARAMETER_TYPE_CHANGED"
    PARAMETER_REQUIRED_NOW = "PARAMETER_REQUIRED_NOW"
    RETURN_TYPE_NARROWED = "RETURN_TYPE_NARROWED"
    RETURN_TYPE_CHANGED = "RETURN_TYPE_CHANGED"
    EXCEPTION_REMOVED = "EXCEPTION_REMOVED"
    EXCEPTION_ADDED = "EXCEPTION_ADDED"
    PRECONDITION_ADDED = "PRECONDITION_ADDED"
    POSTCONDITION_REMOVED = "POSTCONDITION_REMOVED"


class ChangeSeverity:
    """Constants for change severity levels."""

    HIGH = "HIGH"  # Will break many callers
    MEDIUM = "MEDIUM"  # Will break some callers
    LOW = "LOW"  # May affect edge cases


class ChangeCategory:
    """Categories of non-breaking changes."""

    PARAMETER_ADDED_OPTIONAL = "PARAMETER_ADDED_OPTIONAL"
    PARAMETER_RENAMED = "PARAMETER_RENAMED"
    RETURN_TYPE_BROADENED = "RETURN_TYPE_BROADENED"
    PRECONDITION_REMOVED = "PRECONDITION_REMOVED"
    POSTCONDITION_ADDED = "POSTCONDITION_ADDED"
    EXCEPTION_REMOVED = "EXCEPTION_REMOVED"
