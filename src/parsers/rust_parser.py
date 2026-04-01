"""Rust language parser using Tree-sitter."""

from typing import List, Optional

from loguru import logger

from src.parsers.base_parser import BaseParser
from src.parsers.symbol import Symbol

try:
    import tree_sitter as ts
    from tree_sitter_rust import language as rust_language

    HAS_RUST_PARSER = True
except ImportError:
    HAS_RUST_PARSER = False
    logger.warning("Tree-sitter Rust not installed. Rust parsing unavailable.")


class RustParser(BaseParser):
    """Extract symbols from Rust source code."""

    LANGUAGE = "rust"
    EXTENSIONS = [".rs"]

    def __init__(self, base_path: str = ""):
        """Initialize Rust parser.

        Args:
            base_path: Root directory for resolving modules
        """
        super().__init__(base_path)

        if not HAS_RUST_PARSER:
            logger.error("Rust parser not available: tree-sitter-rust not installed")
            self.parser = None
            return

        try:
            self.parser = ts.Parser()
            self.parser.set_language(rust_language())
        except Exception as e:
            logger.error(f"Failed to initialize Rust parser: {e}")
            self.parser = None

    def parse_file(self, file_path: str) -> List[Symbol]:
        """Parse a Rust file and extract symbols.

        Args:
            file_path: Path to .rs file

        Returns:
            List of symbols found in file
        """
        if not self.parser:
            logger.warning(f"Rust parser not available; skipping {file_path}")
            return []

        source_code = self._read_file(file_path)
        if not source_code:
            return []

        try:
            tree = self.parser.parse(source_code.encode("utf-8"))
            symbols = self._extract_symbols(source_code, file_path, tree)
            self._log_parsing(file_path, len(symbols))
            return symbols
        except Exception as e:
            logger.error(f"Failed to parse {file_path}: {e}")
            return []

    def _extract_symbols(
        self, source_code: str, file_path: str, tree
    ) -> List[Symbol]:
        """Extract symbols from parsed Rust AST.

        Extracts:
        - Functions
        - Structs
        - Traits
        - Impl blocks (methods)
        - Enums
        - Modules

        Args:
            source_code: Source code text
            file_path: Path to file
            tree: Tree-sitter tree

        Returns:
            List of symbols
        """
        symbols = []

        # 1. Function declarations
        for node in self._find_nodes(tree.root_node, "function_item"):
            name = self._get_child_text(node, source_code, "name")
            if name:
                symbols.append(
                    Symbol(
                        name=name,
                        type="function",
                        file=file_path,
                        line=node.start_point[0] + 1,
                        column=node.start_point[1],
                    )
                )

        # 2. Struct declarations
        for node in self._find_nodes(tree.root_node, "struct_item"):
            name = self._get_child_text(node, source_code, "name")
            if name:
                symbols.append(
                    Symbol(
                        name=name,
                        type="struct",
                        file=file_path,
                        line=node.start_point[0] + 1,
                        column=node.start_point[1],
                    )
                )

        # 3. Trait declarations
        for node in self._find_nodes(tree.root_node, "trait_item"):
            name = self._get_child_text(node, source_code, "name")
            if name:
                symbols.append(
                    Symbol(
                        name=name,
                        type="trait",
                        file=file_path,
                        line=node.start_point[0] + 1,
                        column=node.start_point[1],
                    )
                )

        # 4. Enum declarations
        for node in self._find_nodes(tree.root_node, "enum_item"):
            name = self._get_child_text(node, source_code, "name")
            if name:
                symbols.append(
                    Symbol(
                        name=name,
                        type="enum",
                        file=file_path,
                        line=node.start_point[0] + 1,
                        column=node.start_point[1],
                    )
                )

        # 5. Module declarations
        for node in self._find_nodes(tree.root_node, "mod_item"):
            name = self._get_child_text(node, source_code, "name")
            if name:
                symbols.append(
                    Symbol(
                        name=name,
                        type="module",
                        file=file_path,
                        line=node.start_point[0] + 1,
                        column=node.start_point[1],
                    )
                )

        # 6. Impl blocks (methods on structs/traits)
        for impl_node in self._find_nodes(tree.root_node, "impl_item"):
            impl_target = self._get_impl_target(impl_node, source_code)
            if not impl_target:
                continue

            # Find methods in impl block
            for func_node in self._find_nodes(impl_node, "function_item"):
                func_name = self._get_child_text(func_node, source_code, "name")
                if func_name:
                    symbols.append(
                        Symbol(
                            name=f"{impl_target}.{func_name}",
                            type="method",
                            file=file_path,
                            line=func_node.start_point[0] + 1,
                            column=func_node.start_point[1],
                            parent=impl_target,
                        )
                    )

        return symbols

    def _find_nodes(self, node, node_type: str) -> List:
        """Find all nodes of a given type in tree.

        Args:
            node: Root node to search from
            node_type: Type of node to find

        Returns:
            List of matching nodes
        """
        results = []

        def traverse(n):
            if n.type == node_type:
                results.append(n)
            for child in n.children:
                traverse(child)

        traverse(node)
        return results

    def _get_child_text(
        self, node, source_code: str, child_type: str
    ) -> Optional[str]:
        """Get text from named child.

        Args:
            node: Parent node
            source_code: Source code
            child_type: Type of child to find

        Returns:
            Text content, or None if not found
        """
        try:
            for child in node.children:
                if hasattr(child, "type") and child.type == child_type:
                    text = source_code[child.start_byte : child.end_byte].strip()
                    return text if text else None
        except Exception:
            pass

        return None

    def _get_impl_target(self, impl_node, source_code: str) -> Optional[str]:
        """Extract the target type from impl block.

        Args:
            impl_node: impl_item node
            source_code: Source code

        Returns:
            Type name being implemented, or None
        """
        try:
            # Look for the type being implemented
            # Pattern: impl Type or impl<T> Type or impl Trait for Type
            text = source_code[impl_node.start_byte : impl_node.end_byte]

            # Simple heuristic: find the last identifier before { or where
            for keyword in ["{", "where"]:
                if keyword in text:
                    before_brace = text[: text.index(keyword)].strip()
                    # Get the last word (type name)
                    words = before_brace.split()
                    for word in reversed(words):
                        # Skip keywords and symbols
                        if word not in ["impl", "for", "<", ">", "&", "*"]:
                            return word.rstrip(">").rstrip("*").rstrip("&")

        except Exception:
            pass

        return None

    def extract_imports(self, file_path: str) -> List[dict]:
        """Extract use statements from Rust file.

        Args:
            file_path: Path to .rs file

        Returns:
            List of imports with module path
        """
        if not self.parser:
            return []

        source_code = self._read_file(file_path)
        if not source_code:
            return []

        imports = []
        try:
            tree = self.parser.parse(source_code.encode("utf-8"))

            for node in self._find_nodes(tree.root_node, "use_declaration"):
                # Extract use path
                use_path = self._extract_use_path(node, source_code)
                if use_path:
                    imports.append(
                        {
                            "module": use_path,
                            "alias": None,
                            "line": node.start_point[0] + 1,
                        }
                    )

        except Exception as e:
            logger.warning(f"Failed to extract imports from {file_path}: {e}")

        return imports

    def _extract_use_path(self, use_node, source_code: str) -> Optional[str]:
        """Extract the module path from a use declaration.

        Args:
            use_node: use_declaration node
            source_code: Source code

        Returns:
            Module path, or None if extraction fails
        """
        try:
            # Get all text and parse it
            text = source_code[use_node.start_byte : use_node.end_byte].strip()

            # Remove 'use ' prefix and ';' suffix
            if text.startswith("use "):
                text = text[4:]
            if text.endswith(";"):
                text = text[:-1]

            return text.strip()
        except Exception:
            pass

        return None
