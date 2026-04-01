"""MCP tools for contract extraction and comparison."""

from mcp.server.fastmcp import Context

from src.contracts.breaking_change_detector import BreakingChangeDetector
from src.contracts.contract_models import ContractComparison, FunctionContract
from src.contracts.extractor import ContractExtractor
from src.mcp_server._app import mcp
from src.mcp_server.services import ServiceContainer
from src.parsers.symbol import Symbol


def _contract_to_dict(contract: FunctionContract) -> dict:
    """Convert FunctionContract dataclass to plain dict for JSON serialization."""
    return {
        "symbol_name": contract.symbol.name,
        "file": contract.symbol.file,
        "signature": {
            "parameters": [
                {
                    "name": p.name,
                    "type_hint": p.type_hint,
                    "is_optional": p.is_optional,
                    "default_value": p.default_value,
                }
                for p in contract.signature.parameters
            ],
            "return_type": contract.signature.return_type,
            "raises": contract.signature.raises,
        },
        "docstring": contract.docstring,
        "preconditions": contract.preconditions,
        "postconditions": contract.postconditions,
        "version": contract.version,
    }


def _comparison_to_dict(comparison: ContractComparison) -> dict:
    """Convert ContractComparison dataclass to plain dict."""
    return {
        "symbol": comparison.old_contract.symbol.name,
        "is_compatible": comparison.is_compatible,
        "compatibility_score": comparison.compatibility_score,
        "breaking_changes": [
            {
                "type": bc.type,
                "severity": bc.severity,
                "impact": bc.impact,
                "affected_elements": list(bc.affected_elements),
                "old_value": bc.old_value,
                "new_value": bc.new_value,
            }
            for bc in comparison.breaking_changes
        ],
        "non_breaking_changes": comparison.non_breaking_changes,
    }


@mcp.tool()
async def extract_contract(
    symbol_name: str,
    file_path: str,
    source_code: str,
    class_name: str | None = None,
    ctx: Context = None,  # type: ignore
) -> dict:
    """
    Extract the function contract (signature, type hints, pre/postconditions)
    from Python source code for the named symbol.

    Args:
        symbol_name: Name of the function to extract.
        file_path: Path to the file containing the function.
        source_code: Full Python source code.
        class_name: Optional class name if function is a method.
        ctx: MCP context (injected by framework, not a tool argument).

    Returns:
        Dict with keys: symbol_name, file, signature (with parameters,
        return_type, raises), docstring, preconditions, postconditions, version.

    Raises:
        ValueError: If symbol not found in source or parsing fails.
    """
    # ContractExtractor is stateless; instantiate per-call
    extractor = ContractExtractor(source_code)

    symbol = Symbol(
        name=symbol_name,
        type="function",
        file=file_path,
        line=1,
        column=0,
        parent=class_name,
    )

    contract = extractor.extract_function_contract(symbol)
    if not contract:
        raise ValueError(f"Function '{symbol_name}' not found in provided source")

    return _contract_to_dict(contract)


@mcp.tool()
async def compare_contracts(
    symbol_name: str,
    old_source: str,
    new_source: str,
    class_name: str | None = None,
    ctx: Context = None,  # type: ignore
) -> dict:
    """
    Compare old and new implementations of a function and detect breaking changes.

    Args:
        symbol_name: Name of the function to compare.
        old_source: Old Python source code.
        new_source: New Python source code.
        class_name: Optional class name if function is a method.
        ctx: MCP context (injected by framework, not a tool argument).

    Returns:
        Dict with keys: symbol, is_compatible, compatibility_score,
        breaking_changes (list), non_breaking_changes (list).
        Each breaking_change has: type, severity, impact, affected_elements,
        old_value, new_value.

    Raises:
        ValueError: If contracts cannot be extracted from either version.
    """
    old_symbol = Symbol(
        name=symbol_name, type="function", file="old.py", line=1, column=0, parent=class_name
    )
    new_symbol = Symbol(
        name=symbol_name, type="function", file="new.py", line=1, column=0, parent=class_name
    )

    old_contract = ContractExtractor(old_source).extract_function_contract(old_symbol)
    new_contract = ContractExtractor(new_source).extract_function_contract(new_symbol)

    if not old_contract or not new_contract:
        raise ValueError("Could not extract contracts from one or both versions")

    comparison = BreakingChangeDetector().detect_breaking_changes(
        old_contract, new_contract
    )

    return _comparison_to_dict(comparison)
