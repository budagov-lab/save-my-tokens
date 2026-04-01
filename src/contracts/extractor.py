"""Extract function contracts from Python source code."""

import ast
import re
from typing import Dict, List, Optional, Tuple

from loguru import logger

from src.contracts.contract_models import (
    FunctionContract,
    ParameterInfo,
    SignatureInfo,
)
from src.parsers.symbol import Symbol


class ContractExtractor:
    """Extract implicit and explicit contracts from Python functions."""

    def __init__(self, source_code: str):
        """Initialize extractor with source code.

        Args:
            source_code: Python source code to parse
        """
        self.source_code = source_code
        try:
            self.tree = ast.parse(source_code)
        except SyntaxError as e:
            logger.error(f"Failed to parse source code: {e}")
            self.tree = None

    def extract_function_contract(
        self, symbol: Symbol
    ) -> Optional[FunctionContract]:
        """Extract contract from a function symbol.

        Args:
            symbol: Symbol representing the function

        Returns:
            FunctionContract with signature, docstring, and type hints, or None if not found
        """
        if not self.tree:
            return None

        # Find the function AST node
        func_node = self._find_function_node(symbol.name, symbol.parent)
        if not func_node:
            logger.warning(f"Could not find AST node for {symbol.qualified_name}")
            return None

        # Extract components
        signature = self._extract_signature(func_node)
        docstring = ast.get_docstring(func_node)
        type_hints = self._extract_type_hints(func_node)
        preconditions = self._extract_preconditions(docstring or "")
        postconditions = self._extract_postconditions(docstring or "")

        return FunctionContract(
            symbol=symbol,
            signature=signature,
            docstring=docstring,
            type_hints=type_hints,
            preconditions=preconditions,
            postconditions=postconditions,
        )

    def _find_function_node(
        self, func_name: str, class_name: Optional[str] = None
    ) -> Optional[ast.FunctionDef]:
        """Find a function AST node by name.

        Args:
            func_name: Function name to find
            class_name: Optional class name (for methods)

        Returns:
            AST FunctionDef node, or None if not found
        """
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef):
                if node.name == func_name:
                    # If class_name specified, find method in that class
                    if class_name:
                        parent = self._find_parent_class(node, class_name)
                        if parent:
                            return node
                    else:
                        # Top-level function
                        if self._is_top_level(node):
                            return node
        return None

    def _is_top_level(self, node: ast.FunctionDef) -> bool:
        """Check if a function is defined at module level."""
        # Simple check: if we find it in direct module body
        for item in self.tree.body:
            if item is node:
                return True
        return False

    def _find_parent_class(
        self, func_node: ast.FunctionDef, class_name: str
    ) -> Optional[ast.ClassDef]:
        """Find the class that contains a method.

        Args:
            func_node: Function node (method)
            class_name: Class name to find

        Returns:
            ClassDef node if found, None otherwise
        """
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef):
                if node.name == class_name:
                    for item in node.body:
                        if item is func_node:
                            return node
        return None

    def _extract_signature(self, func_node: ast.FunctionDef) -> SignatureInfo:
        """Extract function signature information.

        Args:
            func_node: AST FunctionDef node

        Returns:
            SignatureInfo with parameters and return type
        """
        parameters = []
        args = func_node.args

        # Process regular arguments
        arg_names = [arg.arg for arg in args.args]
        arg_annotations = [arg.annotation for arg in args.args]
        arg_defaults = args.defaults

        # Match defaults: defaults are aligned to the right
        num_defaults = len(arg_defaults)
        num_args = len(arg_names)

        for i, arg_name in enumerate(arg_names):
            is_optional = i >= (num_args - num_defaults)
            default_value = None
            type_hint = None

            # Extract type hint if present
            if arg_annotations[i]:
                type_hint = ast.unparse(arg_annotations[i])

            if is_optional:
                default_idx = i - (num_args - num_defaults)
                default_value = ast.unparse(arg_defaults[default_idx])

            param = ParameterInfo(
                name=arg_name,
                type_hint=type_hint,
                is_optional=is_optional,
                default_value=default_value
            )
            parameters.append(param)

        # Process keyword-only arguments
        for arg in args.kwonlyargs:
            # These are optional by definition
            type_hint = ast.unparse(arg.annotation) if arg.annotation else None
            parameters.append(ParameterInfo(name=arg.arg, type_hint=type_hint, is_optional=True))

        # Extract return type
        return_type = None
        if func_node.returns:
            return_type = ast.unparse(func_node.returns)

        # Extract exceptions from docstring
        raises = self._extract_exceptions_from_docstring(
            ast.get_docstring(func_node) or ""
        )

        return SignatureInfo(
            parameters=parameters, return_type=return_type, raises=raises
        )

    def _extract_type_hints(self, func_node: ast.FunctionDef) -> Dict[str, str]:
        """Extract type hints from function.

        Args:
            func_node: AST FunctionDef node

        Returns:
            Dict mapping parameter names to type hint strings
        """
        type_hints = {}
        args = func_node.args

        # Regular arguments
        for arg in args.args:
            if arg.annotation:
                type_hints[arg.arg] = ast.unparse(arg.annotation)

        # Keyword-only arguments
        for arg in args.kwonlyargs:
            if arg.annotation:
                type_hints[arg.arg] = ast.unparse(arg.annotation)

        return type_hints

    def _extract_preconditions(self, docstring: str) -> List[str]:
        """Extract preconditions from docstring.

        Looks for patterns like:
        - "requires X to be Y"
        - "assumes X is Y"
        - "X must be Y"

        Args:
            docstring: Function docstring

        Returns:
            List of precondition strings
        """
        preconditions = []

        # Parse Google-style docstring
        args_section = self._extract_google_section(docstring, "Args")
        if not args_section:
            return preconditions

        # Extract preconditions from Args descriptions
        for line in args_section:
            # Look for patterns like "param (type): description with requirement"
            if "requires" in line.lower() or "must" in line.lower():
                preconditions.append(line.strip())

        return preconditions

    def _extract_postconditions(self, docstring: str) -> List[str]:
        """Extract postconditions from docstring.

        Looks for patterns in the Returns section.

        Args:
            docstring: Function docstring

        Returns:
            List of postcondition strings
        """
        postconditions = []

        # Parse Google-style docstring
        returns_section = self._extract_google_section(docstring, "Returns")
        if not returns_section:
            return postconditions

        # Extract postconditions from Returns descriptions
        for line in returns_section:
            if line.strip():
                postconditions.append(line.strip())

        return postconditions

    def _extract_exceptions_from_docstring(self, docstring: str) -> List[str]:
        """Extract exception types from docstring Raises section.

        Args:
            docstring: Function docstring

        Returns:
            List of exception type names
        """
        exceptions = []

        raises_section = self._extract_google_section(docstring, "Raises")
        if not raises_section:
            return exceptions

        # Parse exception lines: "ExceptionType: description"
        for line in raises_section:
            line = line.strip()
            if line and ":" in line:
                exc_type = line.split(":")[0].strip()
                if exc_type:
                    exceptions.append(exc_type)

        return exceptions

    def _extract_google_section(self, docstring: str, section: str) -> List[str]:
        """Extract a section from a Google-style docstring.

        Args:
            docstring: Full docstring
            section: Section name (e.g., "Args", "Returns", "Raises")

        Returns:
            List of content lines in the section
        """
        lines = docstring.split("\n")
        section_lower = section.lower()
        in_section = False
        result = []

        for line in lines:
            stripped = line.strip()

            # Check for section header
            if stripped.lower().startswith(section_lower + ":"):
                in_section = True
                continue

            # Check for end of section (next header)
            if in_section and stripped.endswith(":") and not stripped.startswith(" "):
                break

            # Collect lines in section
            if in_section and stripped:
                result.append(line)

        return result
