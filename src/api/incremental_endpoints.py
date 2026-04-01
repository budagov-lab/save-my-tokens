"""API endpoints for incremental updates."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from loguru import logger
from pydantic import BaseModel

from src.incremental.diff_parser import DiffParser
from src.incremental.symbol_delta import SymbolDelta, UpdateResult
from src.incremental.updater import IncrementalSymbolUpdater
from src.parsers.symbol_index import SymbolIndex
from src.graph.neo4j_client import Neo4jClient


# Request/Response Models
class SymbolInfo(BaseModel):
    """Information about a symbol."""

    name: str
    type: str
    file: str
    line: int
    column: int
    parent: Optional[str] = None
    qualified_name: str


class FileDiffInfo(BaseModel):
    """Information about file changes."""

    file_path: str
    status: str  # added, modified, deleted, renamed
    added_lines: int
    deleted_lines: int


class DiffRequest(BaseModel):
    """Request for incremental update from git diff."""

    diff_content: str
    base_commit: Optional[str] = None  # For validation


class DiffSummaryResponse(BaseModel):
    """Summary of changes in a diff."""

    total_files_changed: int
    total_lines_added: int
    total_lines_deleted: int
    files: List[FileDiffInfo]


class UpdateDeltaRequest(BaseModel):
    """Request to apply a symbol delta."""

    file: str
    added_symbols: List[SymbolInfo] = []
    deleted_symbol_names: List[str] = []
    modified_symbols: List[SymbolInfo] = []


class UpdateDeltaResponse(BaseModel):
    """Response from applying a delta."""

    success: bool
    file: str
    duration_ms: float
    error: Optional[str] = None
    added: int
    deleted: int
    modified: int


class ConsistencyCheckResponse(BaseModel):
    """Response from consistency validation."""

    is_consistent: bool
    errors: List[str] = []
    warnings: List[str] = []
    timestamp: str


def create_incremental_router(
    symbol_index: SymbolIndex, neo4j_client: Neo4jClient
) -> APIRouter:
    """Create router for incremental update endpoints.

    Args:
        symbol_index: In-memory symbol index
        neo4j_client: Neo4j client

    Returns:
        APIRouter with configured endpoints
    """
    router = APIRouter(prefix="/api/incremental", tags=["incremental"])
    updater = IncrementalSymbolUpdater(symbol_index, neo4j_client)
    diff_parser = DiffParser()

    @router.post("/diff-summary", response_model=DiffSummaryResponse)
    async def get_diff_summary(request: DiffRequest) -> DiffSummaryResponse:
        """Parse a git diff and return summary of changes.

        This endpoint identifies which files changed and their change type
        (added, modified, deleted, renamed).

        Args:
            request: DiffRequest with git diff content

        Returns:
            Summary of changes
        """
        try:
            summary = diff_parser.parse_diff(request.diff_content)
            files = [
                FileDiffInfo(
                    file_path=f.file_path,
                    status=f.status,
                    added_lines=f.added_lines,
                    deleted_lines=f.deleted_lines,
                )
                for f in summary.files
            ]

            return DiffSummaryResponse(
                total_files_changed=summary.total_files_changed,
                total_lines_added=summary.total_lines_added,
                total_lines_deleted=summary.total_lines_deleted,
                files=files,
            )

        except Exception as e:
            logger.error(f"Failed to parse diff: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid diff format: {str(e)}",
            )

    @router.post("/apply-delta", response_model=UpdateDeltaResponse)
    async def apply_delta(request: UpdateDeltaRequest) -> UpdateDeltaResponse:
        """Apply a symbol delta to update the graph.

        This endpoint applies changes to both the in-memory index and Neo4j.
        All operations are transactional: either all succeed or all rollback.

        Args:
            request: UpdateDeltaRequest with symbol changes

        Returns:
            Result of applying the delta
        """
        try:
            # Convert request to internal SymbolDelta format
            from src.parsers.symbol import Symbol

            added_symbols = [
                Symbol(
                    name=s.name,
                    type=s.type,
                    file=s.file,
                    line=s.line,
                    column=s.column,
                    parent=s.parent,
                )
                for s in request.added_symbols
            ]

            modified_symbols = [
                Symbol(
                    name=s.name,
                    type=s.type,
                    file=s.file,
                    line=s.line,
                    column=s.column,
                    parent=s.parent,
                )
                for s in request.modified_symbols
            ]

            delta = SymbolDelta(
                file=request.file,
                added=added_symbols,
                deleted=request.deleted_symbol_names,
                modified=modified_symbols,
            )

            # Apply delta
            result = updater.apply_delta(delta)

            if not result.success:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Failed to apply delta: {result.error}",
                )

            return UpdateDeltaResponse(
                success=True,
                file=request.file,
                duration_ms=result.duration_ms,
                added=len(added_symbols),
                deleted=len(request.deleted_symbol_names),
                modified=len(modified_symbols),
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to apply delta: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid delta: {str(e)}",
            )

    @router.post("/validate-consistency", response_model=ConsistencyCheckResponse)
    async def validate_consistency() -> ConsistencyCheckResponse:
        """Validate graph consistency after updates.

        Checks:
        1. Referential integrity (edges have valid nodes)
        2. Symbol uniqueness per file
        3. Valid edge types

        Returns:
            Consistency check result
        """
        try:
            from datetime import datetime

            is_consistent = updater.validate_graph_consistency()

            return ConsistencyCheckResponse(
                is_consistent=is_consistent,
                errors=[] if is_consistent else ["Graph consistency check failed"],
                timestamp=datetime.utcnow().isoformat(),
            )

        except Exception as e:
            logger.error(f"Consistency validation failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Consistency check error: {str(e)}",
            )

    @router.get("/delta-history")
    async def get_delta_history() -> dict:
        """Get history of applied deltas.

        Returns:
            List of deltas applied in this session
        """
        return {
            "count": len(updater.delta_history),
            "deltas": [
                {
                    "file": d.file,
                    "timestamp": d.timestamp.isoformat(),
                    "added": len(d.added),
                    "deleted": len(d.deleted),
                    "modified": len(d.modified),
                }
                for d in updater.delta_history
            ],
        }

    return router
