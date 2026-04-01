"""Java language parser using Tree-sitter."""

from typing import List, Optional

from loguru import logger

from src.parsers.base_parser import BaseParser
from src.parsers.symbol import Symbol

try:
    import tree_sitter as ts
    from tree_sitter_java import language as java_language

    HAS_JAVA_PARSER = True
except ImportError:
    HAS_JAVA_PARSER = False
    logger.warning("Tree-sitter Java not installed. Java parsing unavailable.")


class JavaParser(BaseParser):
    """Extract symbols from Java source code."""

    LANGUAGE = "java"
    EXTENSIONS = [".java"]

    def __init__(self, base_path: str = ""):
        """Initialize Java parser.

        Args:
            base_path: Root directory for resolving packages
        """
        super().__init__(base_path)

        if not HAS_JAVA_PARSER:
            logger.error("Java parser not available: tree-sitter-java not installed")
            self.parser = None
            return

        try:
            self.parser = ts.Parser()
            self.parser.set_language(java_language())
        except Exception as e:
            logger.error(f"Failed to initialize Java parser: {e}")
            self.parser = None

    def parse_file(self, file_path: str) -> List[Symbol]:
        """Parse a Java file and extract symbols.

        Args:
            file_path: Path to .java file

        Returns:
            List of symbols found in file
        """
        if not self.parser:
            logger.warning(f"Java parser not available; skipping {file_path}")
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
        """Extract symbols from parsed Java AST.

        Extracts:
        - Class declarations and methods
        - Interface declarations and methods
        - Enum declarations

        Args:
            source_code: Source code text
            file_path: Path to file
            tree: Tree-sitter tree

        Returns:
            List of symbols
        """
        symbols = []

        # 1. Class declarations and their methods
        for class_node in self._find_nodes(tree.root_node, "class_declaration"):
            class_name = self._get_child_text(class_node, source_code, "name")
            if not class_name:
                continue

            symbols.append(
                Symbol(
                    name=class_name,
                    type="class",
                    file=file_path,
                    line=class_node.start_point[0] + 1,
                    column=class_node.start_point[1],
                )
            )

            # Extract methods in class
            for method_node in self._find_nodes(class_node, "method_declaration"):
                method_name = self._get_child_text(method_node, source_code, "name")
                if method_name:
                    symbols.append(
                        Symbol(
                            name=f"{class_name}.{method_name}",
                            type="method",
                            file=file_path,
                            line=method_node.start_point[0] + 1,
                            column=method_node.start_point[1],
                            parent=class_name,
                        )
                    )

            # Also extract constructors
            for constructor_node in self._find_nodes(
                class_node, "constructor_declaration"
            ):
                constructor_name = self._get_child_text(
                    constructor_node, source_code, "name"
                )
                if constructor_name:
                    symbols.append(
                        Symbol(
                            name=f"{class_name}.{constructor_name}",
                            type="constructor",
                            file=file_path,
                            line=constructor_node.start_point[0] + 1,
                            column=constructor_node.start_point[1],
                            parent=class_name,
                        )
                    )

        # 2. Interface declarations and their methods
        for interface_node in self._find_nodes(
            tree.root_node, "interface_declaration"
        ):
            interface_name = self._get_child_text(interface_node, source_code, "name")
            if not interface_name:
                continue

            symbols.append(
                Symbol(
                    name=interface_name,
                    type="interface",
                    file=file_path,
                    line=interface_node.start_point[0] + 1,
                    column=interface_node.start_point[1],
                )
            )

            # Extract methods in interface
            for method_node in self._find_nodes(
                interface_node, "method_declaration"
            ):
                method_name = self._get_child_text(method_node, source_code, "name")
                if method_name:
                    symbols.append(
                        Symbol(
                            name=f"{interface_name}.{method_name}",
                            type="method",
                            file=file_path,
                            line=method_node.start_point[0] + 1,
                            column=method_node.start_point[1],
                            parent=interface_name,
                        )
                    )

        # 3. Enum declarations
        for enum_node in self._find_nodes(tree.root_node, "enum_declaration"):
            enum_name = self._get_child_text(enum_node, source_code, "name")
            if enum_name:
                symbols.append(
                    Symbol(
                        name=enum_name,
                        type="enum",
                        file=file_path,
                        line=enum_node.start_point[0] + 1,
                        column=enum_node.start_point[1],
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

    def extract_imports(self, file_path: str) -> List[dict]:
        """Extract import statements from Java file.

        Args:
            file_path: Path to .java file

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

            for node in self._find_nodes(tree.root_node, "import_declaration"):
                # Extract import path
                import_path = self._extract_import_path(node, source_code)
                if import_path:
                    imports.append(
                        {
                            "module": import_path,
                            "alias": None,
                            "line": node.start_point[0] + 1,
                        }
                    )

        except Exception as e:
            logger.warning(f"Failed to extract imports from {file_path}: {e}")

        return imports

    def _extract_import_path(self, import_node, source_code: str) -> Optional[str]:
        """Extract the package path from an import declaration.

        Args:
            import_node: import_declaration node
            source_code: Source code

        Returns:
            Package path, or None if extraction fails
        """
        try:
            # Get all text
            text = source_code[import_node.start_byte : import_node.end_byte].strip()

            # Remove 'import ' prefix and ';' suffix
            if text.startswith("import "):
                text = text[7:]
            if text.startswith("static "):
                text = text[7:]
            if text.endswith(";"):
                text = text[:-1]

            return text.strip()
        except Exception:
            pass

        return None
