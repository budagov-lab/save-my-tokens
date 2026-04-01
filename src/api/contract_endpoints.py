"""API endpoints for contract extraction and validation."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from loguru import logger
from pydantic import BaseModel

from src.contracts.breaking_change_detector import BreakingChangeDetector
from src.contracts.extractor import ContractExtractor
from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex


# Request/Response Models
class ContractParameterResponse(BaseModel):
    """Information about a contract parameter."""

    name: str
    type_hint: Optional[str] = None
    is_optional: bool
    default_value: Optional[str] = None


class SignatureResponse(BaseModel):
    """Function signature information."""

    parameters: List[ContractParameterResponse]
    return_type: Optional[str] = None
    raises: List[str] = []


class ContractResponse(BaseModel):
    """Function contract response."""

    symbol_name: str
    file: str
    signature: SignatureResponse
    docstring: Optional[str] = None
    preconditions: List[str] = []
    postconditions: List[str] = []
    version: str = "1.0"


class BreakingChangeResponse(BaseModel):
    """Breaking change in contract."""

    type: str
    severity: str  # HIGH, MEDIUM, LOW
    impact: str
    affected_elements: List[str] = []
    old_value: Optional[str] = None
    new_value: Optional[str] = None


class ContractComparisonResponse(BaseModel):
    """Result of comparing two contracts."""

    symbol: str
    old_version: str
    new_version: str
    is_compatible: bool
    compatibility_score: float  # 0-1
    breaking_changes: List[BreakingChangeResponse] = []
    non_breaking_changes: List[str] = []


class ExtractContractRequest(BaseModel):
    """Request to extract a function contract."""

    symbol_name: str
    file_path: str
    source_code: str


class CompareContractsRequest(BaseModel):
    """Request to compare two contracts."""

    old_source: str
    new_source: str
    symbol_name: str
    class_name: Optional[str] = None


def create_contract_router(symbol_index: SymbolIndex) -> APIRouter:
    """Create router for contract endpoints.

    Args:
        symbol_index: In-memory symbol index

    Returns:
        APIRouter with configured endpoints
    """
    router = APIRouter(prefix="/api/contracts", tags=["contracts"])

    @router.post("/extract", response_model=ContractResponse)
    async def extract_contract(request: ExtractContractRequest) -> ContractResponse:
        """Extract contract from a function.

        Args:
            request: Extraction request with source code and symbol info

        Returns:
            Extracted contract
        """
        try:
            extractor = ContractExtractor(request.source_code)

            # Create symbol
            symbol = Symbol(
                name=request.symbol_name,
                type="function",
                file=request.file_path,
                line=1,
                column=0,
            )

            # Extract contract
            contract = extractor.extract_function_contract(symbol)

            if not contract:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Function '{request.symbol_name}' not found in source",
                )

            # Convert to response
            params = [
                ContractParameterResponse(
                    name=p.name,
                    type_hint=p.type_hint,
                    is_optional=p.is_optional,
                    default_value=p.default_value,
                )
                for p in contract.signature.parameters
            ]

            signature = SignatureResponse(
                parameters=params,
                return_type=contract.signature.return_type,
                raises=contract.signature.raises,
            )

            return ContractResponse(
                symbol_name=contract.symbol.name,
                file=contract.symbol.file,
                signature=signature,
                docstring=contract.docstring,
                preconditions=contract.preconditions,
                postconditions=contract.postconditions,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to extract contract: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Contract extraction failed: {str(e)}",
            )

    @router.post("/compare", response_model=ContractComparisonResponse)
    async def compare_contracts(request: CompareContractsRequest) -> ContractComparisonResponse:
        """Compare two versions of a function contract.

        Detects breaking changes between old and new implementations.

        Args:
            request: Comparison request with old/new source

        Returns:
            Comparison result with breaking changes
        """
        try:
            # Extract contracts from both versions
            old_extractor = ContractExtractor(request.old_source)
            new_extractor = ContractExtractor(request.new_source)

            old_symbol = Symbol(
                name=request.symbol_name,
                type="function",
                file="old.py",
                line=1,
                column=0,
                parent=request.class_name,
            )

            new_symbol = Symbol(
                name=request.symbol_name,
                type="function",
                file="new.py",
                line=1,
                column=0,
                parent=request.class_name,
            )

            old_contract = old_extractor.extract_function_contract(old_symbol)
            new_contract = new_extractor.extract_function_contract(new_symbol)

            if not old_contract or not new_contract:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Could not extract contracts from both versions",
                )

            # Detect breaking changes
            detector = BreakingChangeDetector()
            comparison = detector.detect_breaking_changes(old_contract, new_contract)

            # Convert to response
            breaking_changes = [
                BreakingChangeResponse(
                    type=bc.type,
                    severity=bc.severity,
                    impact=bc.impact,
                    affected_elements=list(bc.affected_elements),
                    old_value=bc.old_value,
                    new_value=bc.new_value,
                )
                for bc in comparison.breaking_changes
            ]

            return ContractComparisonResponse(
                symbol=request.symbol_name,
                old_version="1.0",
                new_version="1.1",
                is_compatible=comparison.is_compatible,
                compatibility_score=comparison.compatibility_score,
                breaking_changes=breaking_changes,
                non_breaking_changes=comparison.non_breaking_changes,
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to compare contracts: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Contract comparison failed: {str(e)}",
            )

    return router
