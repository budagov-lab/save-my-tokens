"""Static analysis for detecting function calls in code."""

from typing import Dict, List, Optional, Set

from tree_sitter import Node as TSNode

from src.parsers.symbol import Symbol
from src.parsers.symbol_index import SymbolIndex


class CallAnalyzer:
    """Analyze function calls using static analysis."""

    def __init__(self, symbol_index: SymbolIndex):
        """Initialize call analyzer.

        Args:
            symbol_index: Symbol index for name resolution
        """
        self.symbol_index = symbol_index

    def extract_calls(
        self,
        function_node: TSNode,
        source_code: bytes,
        file_path: str,
        body_node_type: str,
        call_node_type: str,
    ) -> List[str]:
        """Unified call extraction for any language.

        Args:
            function_node: Tree-sitter node for function definition
            source_code: Source code bytes
            file_path: File path of the source
            body_node_type: Type of body node ("block" for Python, "statement_block" for TypeScript)
            call_node_type: Type of call node ("call" for Python, "call_expression" for TypeScript)

        Returns:
            List of called function node_ids
        """
        calls: Set[str] = set()

        # Find function body
        body_node = next(
            (c for c in function_node.children if c.type == body_node_type), None
        )

        if not body_node:
            return []

        # Recursively find all call nodes
        self._find_call_nodes(body_node, source_code, file_path, call_node_type, calls)
        return list(calls)

    def extract_calls_python(
        self, function_node: TSNode, source_code: bytes, file_path: str
    ) -> List[str]:
        """Extract function calls from a Python function body.

        Args:
            function_node: Tree-sitter node for function definition
            source_code: Source code bytes
            file_path: File path of the source

        Returns:
            List of called function node_ids
        """
        return self.extract_calls(
            function_node, source_code, file_path, "block", "call"
        )

    def extract_calls_typescript(
        self, function_node: TSNode, source_code: bytes, file_path: str
    ) -> List[str]:
        """Extract function calls from a TypeScript/JavaScript function body.

        Args:
            function_node: Tree-sitter node for function definition
            source_code: Source code bytes
            file_path: File path of the source

        Returns:
            List of called function node_ids
        """
        return self.extract_calls(
            function_node, source_code, file_path, "statement_block", "call_expression"
        )

    def _find_call_nodes(
        self,
        node: TSNode,
        source_code: bytes,
        file_path: str,
        call_node_type: str,
        calls: Set[str],
    ) -> None:
        """Recursively find call nodes in AST (unified for all languages).

        Args:
            node: Current tree-sitter node
            source_code: Source code bytes
            file_path: File path of source
            call_node_type: Type of call node ("call" or "call_expression")
            calls: Set to accumulate found calls
        """
        if node.type == call_node_type:
            # Extract the function name being called
            func_node = node.child_by_field_name("function")
            if func_node:
                func_name = source_code[
                    func_node.start_byte : func_node.end_byte
                ].decode("utf-8")
                resolved = self._resolve_call_name(func_name, file_path)
                if resolved:
                    calls.add(resolved)

        # Recurse into children
        for child in node.children:
            self._find_call_nodes(child, source_code, file_path, call_node_type, calls)

    def _find_call_nodes_python(
        self, node: TSNode, source_code: bytes, file_path: str, calls: Set[str]
    ) -> None:
        """Recursively find call nodes in Python AST.

        Wrapper around _find_call_nodes() for backward compatibility.

        Args:
            node: Current tree-sitter node
            source_code: Source code bytes
            file_path: File path of source
            calls: Set to accumulate found calls
        """
        self._find_call_nodes(node, source_code, file_path, "call", calls)

    def _find_call_nodes_typescript(
        self, node: TSNode, source_code: bytes, file_path: str, calls: Set[str]
    ) -> None:
        """Recursively find call nodes in TypeScript AST.

        Wrapper around _find_call_nodes() for backward compatibility.

        Args:
            node: Current tree-sitter node
            source_code: Source code bytes
            file_path: File path of source
            calls: Set to accumulate found calls
        """
        self._find_call_nodes(node, source_code, file_path, "call_expression", calls)

    def _resolve_call_name(self, call_name: str, file_path: str) -> Optional[str]:
        """Resolve a called function name to a node_id.

        Simple heuristic: look up in symbol index by name.
        For qualified calls (a.b.c), try to resolve using import context.

        Args:
            call_name: Name as it appears in the code (possibly with module prefix)
            file_path: File making the call

        Returns:
            node_id of called function, or None if not resolvable
        """
        call_name = call_name.strip()

        # Handle simple names (no dots)
        if "." not in call_name:
            candidates = self.symbol_index.get_by_name(call_name)
            # Prefer local definitions (in same file)
            local = [c for c in candidates if c.file == file_path]
            if local:
                return local[0].node_id
            # Fallback to any match
            if candidates:
                return candidates[0].node_id
            return None

        # Handle qualified names (module.function, obj.method)
        # Try to match using qualified_name
        parts = call_name.split(".")
        # Look for symbol matching last part
        last_part = parts[-1]
        candidates = self.symbol_index.get_by_name(last_part)
        if candidates:
            return candidates[0].node_id
        return None
