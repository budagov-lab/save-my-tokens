"""Integration tests for contract extraction and validation."""

import textwrap

import pytest

from src.contracts.breaking_change_detector import BreakingChangeDetector
from src.contracts.contract_models import (
    BreakingChangeType,
    ChangeSeverity,
    ParameterInfo,
    SignatureInfo,
)
from src.contracts.extractor import ContractExtractor
from src.parsers.symbol import Symbol


class TestContractExtractor:
    """Test suite for ContractExtractor."""

    def test_extract_simple_function_contract(self):
        """Test extracting contract from simple function."""
        source = textwrap.dedent(
            '''
            def add(a: int, b: int) -> int:
                """Add two integers.

                Args:
                    a: First integer
                    b: Second integer

                Returns:
                    Sum of a and b
                """
                return a + b
            '''
        )

        extractor = ContractExtractor(source)
        symbol = Symbol(name="add", type="function", file="test.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None
        assert contract.symbol.name == "add"
        assert contract.signature.return_type == "int"
        assert len(contract.signature.parameters) == 2
        assert contract.signature.parameters[0].name == "a"
        assert contract.signature.parameters[0].type_hint == "int"

    def test_extract_function_with_optional_parameters(self):
        """Test extracting function with optional parameters."""
        source = textwrap.dedent(
            '''
            def greet(name: str, greeting: str = "Hello") -> str:
                """Greet a person.

                Args:
                    name: Person's name
                    greeting: Greeting message (default: "Hello")

                Returns:
                    Greeting string
                """
                return f"{greeting}, {name}!"
            '''
        )

        extractor = ContractExtractor(source)
        symbol = Symbol(name="greet", type="function", file="test.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None
        assert len(contract.signature.parameters) == 2
        assert not contract.signature.parameters[0].is_optional
        assert contract.signature.parameters[1].is_optional
        assert contract.signature.parameters[1].default_value == "'Hello'"

    def test_extract_function_with_exceptions(self):
        """Test extracting function with exceptions in docstring."""
        source = textwrap.dedent(
            '''
            def divide(a: float, b: float) -> float:
                """Divide two numbers.

                Args:
                    a: Dividend
                    b: Divisor

                Returns:
                    Result of a / b

                Raises:
                    ZeroDivisionError: When b is zero
                    ValueError: When inputs are invalid
                """
                if b == 0:
                    raise ZeroDivisionError("Cannot divide by zero")
                return a / b
            '''
        )

        extractor = ContractExtractor(source)
        symbol = Symbol(name="divide", type="function", file="test.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None
        assert "ZeroDivisionError" in contract.signature.raises
        assert "ValueError" in contract.signature.raises

    def test_extract_function_without_docstring(self):
        """Test extracting function without docstring."""
        source = textwrap.dedent(
            '''
            def multiply(a: int, b: int) -> int:
                return a * b
            '''
        )

        extractor = ContractExtractor(source)
        symbol = Symbol(name="multiply", type="function", file="test.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None
        assert contract.docstring is None
        assert len(contract.signature.parameters) == 2
        assert contract.signature.return_type == "int"

    def test_extract_function_without_type_hints(self):
        """Test extracting function without type hints."""
        source = textwrap.dedent(
            '''
            def subtract(a, b):
                """Subtract b from a."""
                return a - b
            '''
        )

        extractor = ContractExtractor(source)
        symbol = Symbol(name="subtract", type="function", file="test.py", line=1, column=0)
        contract = extractor.extract_function_contract(symbol)

        assert contract is not None
        assert contract.signature.parameters[0].type_hint is None
        assert contract.signature.return_type is None


class TestBreakingChangeDetector:
    """Test suite for BreakingChangeDetector."""

    def test_detect_parameter_removed(self):
        """Test detection of removed parameters (breaking)."""
        from src.contracts.contract_models import FunctionContract

        old_contract = FunctionContract(
            symbol=Symbol(name="process", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[
                    ParameterInfo(name="data"),
                    ParameterInfo(name="validate"),
                ],
                return_type="bool",
            ),
        )

        new_contract = FunctionContract(
            symbol=Symbol(name="process", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[ParameterInfo(name="data")],  # validate removed
                return_type="bool",
            ),
        )

        detector = BreakingChangeDetector()
        comparison = detector.detect_breaking_changes(old_contract, new_contract)

        assert not comparison.is_compatible
        assert len(comparison.breaking_changes) == 1
        assert (
            comparison.breaking_changes[0].type
            == BreakingChangeType.PARAMETER_REMOVED
        )
        assert "validate" in comparison.breaking_changes[0].affected_elements
        assert (
            comparison.breaking_changes[0].severity == ChangeSeverity.HIGH
        )

    def test_detect_optional_parameter_added(self):
        """Test that adding optional parameters is non-breaking."""
        from src.contracts.contract_models import FunctionContract

        old_contract = FunctionContract(
            symbol=Symbol(name="process", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[ParameterInfo(name="data")],
                return_type="bool",
            ),
        )

        new_contract = FunctionContract(
            symbol=Symbol(name="process", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[
                    ParameterInfo(name="data"),
                    ParameterInfo(name="validate", is_optional=True),  # Added optional
                ],
                return_type="bool",
            ),
        )

        detector = BreakingChangeDetector()
        comparison = detector.detect_breaking_changes(old_contract, new_contract)

        assert comparison.is_compatible  # Should be compatible
        assert len(comparison.breaking_changes) == 0
        assert len(comparison.non_breaking_changes) > 0

    def test_detect_parameter_became_required(self):
        """Test detection of optional parameter becoming required."""
        from src.contracts.contract_models import FunctionContract

        old_contract = FunctionContract(
            symbol=Symbol(name="process", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[
                    ParameterInfo(name="data"),
                    ParameterInfo(name="validate", is_optional=True),
                ],
                return_type="bool",
            ),
        )

        new_contract = FunctionContract(
            symbol=Symbol(name="process", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[
                    ParameterInfo(name="data"),
                    ParameterInfo(name="validate", is_optional=False),  # Now required
                ],
                return_type="bool",
            ),
        )

        detector = BreakingChangeDetector()
        comparison = detector.detect_breaking_changes(old_contract, new_contract)

        assert not comparison.is_compatible
        assert len(comparison.breaking_changes) == 1
        assert (
            comparison.breaking_changes[0].type
            == BreakingChangeType.PARAMETER_REQUIRED_NOW
        )

    def test_detect_return_type_narrowed(self):
        """Test detection of narrowed return type."""
        from src.contracts.contract_models import FunctionContract

        old_contract = FunctionContract(
            symbol=Symbol(name="get_value", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[],
                return_type="Any",
            ),
        )

        new_contract = FunctionContract(
            symbol=Symbol(name="get_value", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[],
                return_type="int",
            ),
        )

        detector = BreakingChangeDetector()
        comparison = detector.detect_breaking_changes(old_contract, new_contract)

        assert not comparison.is_compatible
        assert len(comparison.breaking_changes) == 1
        assert (
            comparison.breaking_changes[0].type
            == BreakingChangeType.RETURN_TYPE_NARROWED
        )

    def test_detect_exception_added(self):
        """Test detection of newly added exceptions."""
        from src.contracts.contract_models import FunctionContract

        old_contract = FunctionContract(
            symbol=Symbol(name="parse", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[],
                return_type="dict",
                raises=[],
            ),
        )

        new_contract = FunctionContract(
            symbol=Symbol(name="parse", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[],
                return_type="dict",
                raises=["ValueError", "JSONDecodeError"],
            ),
        )

        detector = BreakingChangeDetector()
        comparison = detector.detect_breaking_changes(old_contract, new_contract)

        # Added exceptions are low severity
        low_severity_changes = [
            c for c in comparison.breaking_changes if c.severity == ChangeSeverity.LOW
        ]
        assert len(low_severity_changes) >= 1

    def test_compatibility_score(self):
        """Test that compatibility score is calculated correctly."""
        from src.contracts.contract_models import FunctionContract

        # Fully compatible
        contract1 = FunctionContract(
            symbol=Symbol(name="test", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(parameters=[], return_type="None"),
        )

        detector = BreakingChangeDetector()
        comparison = detector.detect_breaking_changes(contract1, contract1)

        assert comparison.compatibility_score == 1.0
        assert comparison.is_compatible

        # With breaking changes
        old_contract = FunctionContract(
            symbol=Symbol(name="test", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[ParameterInfo(name="x"), ParameterInfo(name="y")],
                return_type="int",
            ),
        )

        new_contract = FunctionContract(
            symbol=Symbol(name="test", type="function", file="test.py", line=1, column=0),
            signature=SignatureInfo(
                parameters=[ParameterInfo(name="x")],  # y removed
                return_type="int",
            ),
        )

        comparison = detector.detect_breaking_changes(old_contract, new_contract)
        assert comparison.compatibility_score < 1.0
        assert not comparison.is_compatible
