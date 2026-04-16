"""Typed Pydantic v2 models for SMTQueryEngine responses.

These models define the contract between the graph layer and consuming agents.
All models are constructed from engine dict output — the engine still returns dicts;
callers can wrap them with these models for type safety and validation.

Usage::

    from src.agents.models import DefinitionResult
    raw = engine.definition("MyFunction")
    result = DefinitionResult.model_validate(raw)
    if result.found:
        print(result.ref.file, result.ref.line)
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------

ErrorReason = Literal["not_found", "graph_stale", "neo4j_offline", "parse_error"]


def _infer_error_reason(data: Any) -> Any:
    """Shared pre-validator: maps raw engine 'error' key to error_reason."""
    if not isinstance(data, dict):
        return data
    if data.get("error") and not data.get("error_reason"):
        msg = str(data["error"])
        if "ServiceUnavailable" in msg or "Unable to connect" in msg or "Connection refused" in msg:
            data = {**data, "error_reason": "neo4j_offline"}
        elif "not found" in msg.lower():
            data = {**data, "error_reason": "not_found"}
        else:
            data = {**data, "error_reason": "parse_error"}
    return data


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------


class SymbolRef(BaseModel):
    """Lightweight reference to a symbol in the graph."""

    model_config = ConfigDict(extra="ignore")

    name: str
    file: Optional[str] = None
    line: Optional[int] = None
    labels: List[str] = Field(default_factory=list)
    signature: Optional[str] = None
    docstring: Optional[str] = None


class EdgeRef(BaseModel):
    """Directed CALLS edge between two symbols."""

    model_config = ConfigDict(extra="ignore")

    src: str
    dst: str


class CycleGroup(BaseModel):
    """A set of mutually recursive symbols collapsed into one representative."""

    model_config = ConfigDict(extra="ignore")

    members: List[str]
    representative: str


class CallerRef(BaseModel):
    """A symbol that calls some target, with location info."""

    model_config = ConfigDict(extra="ignore")

    name: str
    file: Optional[str] = None
    line: Optional[int] = None


# ---------------------------------------------------------------------------
# definition()
# ---------------------------------------------------------------------------


class CalleeRef(BaseModel):
    """Immediate callee returned by definition()."""

    model_config = ConfigDict(extra="ignore")

    name: str
    file: Optional[str] = None


class DefinitionResult(BaseModel):
    """Result of SMTQueryEngine.definition().

    ``found=False`` when the symbol is absent from the graph.
    ``error_reason`` is set when the failure is structural (offline, stale, …).
    """

    model_config = ConfigDict(extra="ignore")

    found: bool
    symbol: Optional[str] = None

    # Populated when found=True
    name: Optional[str] = None
    labels: List[str] = Field(default_factory=list)
    file: Optional[str] = None
    line: Optional[int] = None
    signature: Optional[str] = None
    docstring: Optional[str] = None
    callees: List[CalleeRef] = Field(default_factory=list)

    # Populated when found=False
    error_reason: Optional[ErrorReason] = None
    error_message: Optional[str] = Field(default=None, alias="error")

    @model_validator(mode="before")
    @classmethod
    def _coerce_error(cls, data: Any) -> Any:
        return _infer_error_reason(data)

    @property
    def ref(self) -> Optional[SymbolRef]:
        """Convenience accessor — returns a SymbolRef when found."""
        if not self.found or self.name is None:
            return None
        return SymbolRef(
            name=self.name,
            file=self.file,
            line=self.line,
            labels=self.labels,
            signature=self.signature,
            docstring=self.docstring,
        )


# ---------------------------------------------------------------------------
# context()
# ---------------------------------------------------------------------------


class ContextResult(BaseModel):
    """Result of SMTQueryEngine.context().

    Contains the bounded bidirectional subgraph around a symbol,
    with cycle groups collapsed and optional bridge-function compression.
    """

    model_config = ConfigDict(extra="ignore")

    found: bool
    symbol: Optional[str] = None

    # Populated when found=True
    root: Optional[Dict[str, Any]] = None
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[EdgeRef] = Field(default_factory=list)
    cycles: List[CycleGroup] = Field(default_factory=list)
    compressed: bool = False
    bridges_removed: int = 0
    original_node_count: int = 0
    final_node_count: int = 0
    token_estimate: int = 0
    depth_reached: int = 0

    # Populated when found=False
    error_reason: Optional[ErrorReason] = None
    error_message: Optional[str] = Field(default=None, alias="error")

    @model_validator(mode="before")
    @classmethod
    def _coerce_error(cls, data: Any) -> Any:
        return _infer_error_reason(data)

    @property
    def symbol_refs(self) -> List[SymbolRef]:
        """All nodes as SymbolRef objects."""
        return [
            SymbolRef(
                name=n.get("name", ""),
                file=n.get("file"),
                line=n.get("line"),
                labels=n.get("labels", []),
            )
            for n in self.nodes
        ]


# ---------------------------------------------------------------------------
# impact()
# ---------------------------------------------------------------------------


class ImpactResult(BaseModel):
    """Result of SMTQueryEngine.impact().

    Contains the reverse-traversal caller tree, grouped by hop distance.
    """

    model_config = ConfigDict(extra="ignore")

    found: bool
    symbol: Optional[str] = None

    # Populated when found=True
    root: Optional[Dict[str, Any]] = None
    callers_by_depth: Dict[int, List[CallerRef]] = Field(default_factory=dict)
    total_callers: int = 0
    cycles: List[CycleGroup] = Field(default_factory=list)
    token_estimate: int = 0
    depth_reached: int = 0

    # Populated when found=False
    error_reason: Optional[ErrorReason] = None
    error_message: Optional[str] = Field(default=None, alias="error")

    @model_validator(mode="before")
    @classmethod
    def _coerce_error(cls, data: Any) -> Any:
        return _infer_error_reason(data)

    @model_validator(mode="before")
    @classmethod
    def _coerce_callers_by_depth(cls, data: Any) -> Any:
        """callers_by_depth keys come as ints from Python but may be strings from JSON."""
        if not isinstance(data, dict):
            return data
        cbd = data.get("callers_by_depth")
        if isinstance(cbd, dict) and cbd:
            data = {**data, "callers_by_depth": {int(k): v for k, v in cbd.items()}}
        return data

    def callers_at(self, depth: int) -> List[CallerRef]:
        """Convenience — callers exactly N hops from the root symbol."""
        return self.callers_by_depth.get(depth, [])

    def all_callers(self) -> List[CallerRef]:
        """Flat list of all callers across all depths."""
        result: List[CallerRef] = []
        for depth_list in self.callers_by_depth.values():
            result.extend(depth_list)
        return result


# ---------------------------------------------------------------------------
# search()
# ---------------------------------------------------------------------------


class SearchHit(BaseModel):
    """Single result from a semantic search."""

    model_config = ConfigDict(extra="ignore")

    name: str
    type: str
    file: Optional[str] = None
    line: Optional[int] = None
    score: float
    docstring: Optional[str] = None

    @property
    def ref(self) -> SymbolRef:
        return SymbolRef(name=self.name, file=self.file, line=self.line)


class SearchResult(BaseModel):
    """Wrapper around a list of SearchHit results.

    The engine returns a bare list; this model provides a typed container
    with convenience accessors.
    """

    model_config = ConfigDict(extra="ignore")

    hits: List[SearchHit] = Field(default_factory=list)
    query: Optional[str] = None
    error_reason: Optional[ErrorReason] = None
    error_message: Optional[str] = None

    @classmethod
    def from_list(cls, raw: List[Dict[str, Any]], query: Optional[str] = None) -> "SearchResult":
        """Construct from the bare list the engine returns."""
        return cls(hits=[SearchHit.model_validate(h) for h in raw], query=query)

    @property
    def top(self) -> Optional[SearchHit]:
        """Highest-scoring result, or None if empty."""
        return self.hits[0] if self.hits else None


# ---------------------------------------------------------------------------
# status()
# ---------------------------------------------------------------------------


FreshnessStatus = Literal["fresh", "stale", "unknown"]


class StatusResult(BaseModel):
    """Result of SMTQueryEngine.status()."""

    model_config = ConfigDict(extra="ignore")

    is_fresh: bool
    git_head: str = "unknown"
    graph_head: Optional[str] = None
    commits_behind: int = -1
    node_count: int = 0
    edge_count: int = 0
    freshness_status: FreshnessStatus = "unknown"
    error_message: Optional[str] = Field(default=None, alias="error")

    @property
    def online(self) -> bool:
        """True when the engine successfully reached Neo4j."""
        return self.node_count >= 0 and self.git_head != "unknown"
