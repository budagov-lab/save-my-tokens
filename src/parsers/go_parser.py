"""Go language parser using Tree-sitter."""

from typing import List, Optional

from loguru import logger

from src.parsers.base_parser import BaseParser
from src.parsers.symbol import Symbol

try:
    import tree_sitter as ts
    from tree_sitter_go import language as go_language

    HAS_GO_PARSER = True
except ImportError:
    HAS_GO_PARSER = False
    logger.warning("Tree-sitter Go not installed. Go parsing unavailable.")


class GoParser(BaseParser):
    """Extract symbols from Go source code."""

    LANGUAGE = "go"
    EXTENSIONS = [".go"]

    def __init__(self, base_path: str = ""):
        """Initialize Go parser.

        Args:
            base_path: Root directory for resolving imports
        """
        super().__init__(base_path)

        if not HAS_GO_PARSER:
            logger.error("Go parser not available: tree-sitter-go not installed")
            self.parser = None
            return

        try:
            self.parser = ts.Parser()
            self.parser.set_language(go_language())
        except Exception as e:
            logger.error(f"Failed to initialize Go parser: {e}")
            self.parser = None

    def parse_file(self, file_path: str) -> List[Symbol]:
        """Parse a Go file and extract symbols.

        Args:
            file_path: Path to .go file

        Returns:
            List of symbols found in file
        """
        if not self.parser:
            logger.warning(f"Go parser not available; skipping {file_path}")
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
        """Extract symbols from parsed Go AST.

        Extracts:
        - Top-level functions
        - Type declarations (structs, interfaces)
        - Methods on types

        Args:
            source_code: Source code text
            file_path: Path to file
            tree: Tree-sitter tree

        Returns:
            List of symbols
        """
        symbols = []

        # 1. Top-level functions
        for node in self._find_nodes(tree.root_node, "function_declaration"):
            name = self._get_node_text(node, source_code, "name")
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

        # 2. Type declarations (struct, interface)
        for node in self._find_nodes(tree.root_node, "type_declaration"):
            # Extract the type spec from declaration
            for type_spec in self._find_nodes(node, "type_spec"):
                name = self._get_node_text(type_spec, source_code, "name")
                if not name:
                    continue

                # Determine type (struct, interface, alias, etc.)
                type_kind = self._get_type_kind(type_spec, source_code)

                symbols.append(
                    Symbol(
                        name=name,
                        type=type_kind,
                        file=file_path,
                        line=type_spec.start_point[0] + 1,
                        column=type_spec.start_point[1],
                    )
                )

        # 3. Methods on types (function declarations with receivers)
        for node in self._find_nodes(tree.root_node, "function_declaration"):
            # Check if this is a method (has receiver)
            receiver = self._get_method_receiver(node, source_code)
            if receiver:
                name = self._get_node_text(node, source_code, "name")
                if name:
                    symbols.append(
                        Symbol(
                            name=f"{receiver}.{name}",
                            type="method",
                            file=file_path,
                            line=node.start_point[0] + 1,
                            column=node.start_point[1],
                            parent=receiver,
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

    def _get_node_text(
        self, node, source_code: str, field: Optional[str] = None
    ) -> str:
        """Get text from node, optionally from named field.

        Args:
            node: Tree-sitter node
            source_code: Source code text
            field: Optional named field to extract

        Returns:
            Text content
        """
        try:
            if field:
                field_node = None
                for child in node.children:
                    if hasattr(child, "type") and child.type == field:
                        field_node = child
                        break

                # If not found as child, try named field
                if not field_node:
                    for i in range(node.child_count):
                        child = node.child(i)
                        if hasattr(child, "field_name") and child.field_name == field:
                            field_node = child
                            break

                if field_node:
                    return source_code[
                        field_node.start_byte : field_node.end_byte
                    ].strip()
            else:
                return source_code[node.start_byte : node.end_byte].strip()
        except Exception:
            pass

        return ""

    def _get_type_kind(self, type_spec, source_code: str) -> str:
        """Determine the kind of type (struct, interface, alias).

        Args:
            type_spec: Type spec node
            source_code: Source code

        Returns:
            Type kind: "struct", "interface", or "type"
        """
        # Check the actual type definition
        type_def_text = source_code[type_spec.start_byte : type_spec.end_byte]

        if "struct {" in type_def_text or "struct\n" in type_def_text:
            return "struct"
        elif "interface {" in type_def_text or "interface\n" in type_def_text:
            return "interface"
        else:
            return "type"

    def _get_method_receiver(self, func_node, source_code: str) -> Optional[str]:
        """Extract method receiver from function declaration.

        Go methods have receiver parameter: func (r ReceiverType) Method()

        Args:
            func_node: Function declaration node
            source_code: Source code

        Returns:
            Receiver type name, or None if not a method
        """
        # Look for parameters node
        for child in func_node.children:
            if hasattr(child, "type") and child.type == "parameters":
                # Parse receiver from parameters
                param_text = source_code[child.start_byte : child.end_byte]

                # Simple heuristic: if starts with (name Type), it's a method
                if param_text.startswith("(") and " " in param_text:
                    parts = param_text[1:].split()
                    if len(parts) >= 2:
                        # Skip pointer: (*Type) -> Type
                        receiver = parts[1].lstrip("*").rstrip(")")
                        if not receiver.startswith(")"):  # Not method if malformed
                            return receiver

        return None

    def extract_imports(self, file_path: str) -> List[dict]:
        """Extract import statements from Go file.

        Args:
            file_path: Path to .go file

        Returns:
            List of imports with module and alias
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
                # Extract import spec(s)
                for spec in self._find_nodes(node, "import_spec"):
                    import_path = self._get_node_text(spec, source_code, "path")
                    if import_path:
                        # Remove quotes
                        import_path = import_path.strip('"')

                        # Check for alias
                        alias = self._get_node_text(spec, source_code, "name")

                        imports.append(
                            {
                                "module": import_path,
                                "alias": alias if alias else None,
                                "line": spec.start_point[0] + 1,
                            }
                        )

        except Exception as e:
            logger.warning(f"Failed to extract imports from {file_path}: {e}")

        return imports
