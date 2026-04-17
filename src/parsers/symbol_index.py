"""In-memory symbol index for fast lookups."""

from typing import Dict, List, Optional

from src.parsers.symbol import Symbol


class SymbolIndex:
    """Fast lookup index for symbols by name."""

    def __init__(self):
        """Initialize symbol index."""
        # Simple name -> List[Symbol] (handles duplicates)
        self._by_name: Dict[str, List[Symbol]] = {}

        # Qualified name (e.g., "ClassName.method_name") -> Symbol
        self._by_qualified_name: Dict[str, Symbol] = {}

        # File path -> List[Symbol]
        self._by_file: Dict[str, List[Symbol]] = {}

        # All symbols (for iteration)
        self._all_symbols: List[Symbol] = []

    def add(self, symbol: Symbol) -> None:
        """Add symbol to index."""
        # Add to all_symbols
        self._all_symbols.append(symbol)

        # Index by simple name
        if symbol.name not in self._by_name:
            self._by_name[symbol.name] = []
        self._by_name[symbol.name].append(symbol)

        # Index by qualified name
        self._by_qualified_name[symbol.qualified_name] = symbol

        # Index by file
        if symbol.file not in self._by_file:
            self._by_file[symbol.file] = []
        self._by_file[symbol.file].append(symbol)

    def add_all(self, symbols: List[Symbol]) -> None:
        """Add multiple symbols to index."""
        for symbol in symbols:
            self.add(symbol)

    def remove(self, symbol: Symbol) -> bool:
        """Remove a symbol from all index structures.

        Args:
            symbol: Symbol to remove

        Returns:
            True if symbol was found and removed, False if not found
        """
        # Remove from _all_symbols
        try:
            self._all_symbols.remove(symbol)
        except ValueError:
            return False  # Not in index

        # Remove from _by_name
        name_list = self._by_name.get(symbol.name, [])
        if symbol in name_list:
            name_list.remove(symbol)
        if not name_list:
            del self._by_name[symbol.name]

        # Remove from _by_qualified_name
        self._by_qualified_name.pop(symbol.qualified_name, None)

        # Remove from _by_file
        file_list = self._by_file.get(symbol.file, [])
        if symbol in file_list:
            file_list.remove(symbol)
        if not file_list:
            del self._by_file[symbol.file]

        return True

    def get_by_name(self, name: str) -> List[Symbol]:
        """Get all symbols with given name."""
        return self._by_name.get(name, [])

    def get_by_qualified_name(self, qualified_name: str) -> Optional[Symbol]:
        """Get symbol by qualified name (e.g., 'ClassName.method_name')."""
        return self._by_qualified_name.get(qualified_name)

    def get_by_file(self, file_path: str) -> List[Symbol]:
        """Get all symbols defined in a file."""
        return self._by_file.get(file_path, [])

    def get_all(self) -> List[Symbol]:
        """Get all symbols."""
        return list(self._all_symbols)

    def find(self, name: str, file_path: Optional[str] = None) -> Optional[Symbol]:
        """Find a symbol by name, optionally filtering by file.

        If multiple symbols with the same name exist:
        - If file_path is provided, return the one from that file
        - Otherwise return the first match
        """
        candidates = self.get_by_name(name)

        if not candidates:
            return None

        if file_path:
            for symbol in candidates:
                if symbol.file == file_path:
                    return symbol

        return candidates[0]

    def get_functions(self) -> List[Symbol]:
        """Get all function symbols."""
        return [s for s in self._all_symbols if s.type == "function"]

    def get_classes(self) -> List[Symbol]:
        """Get all class symbols."""
        return [s for s in self._all_symbols if s.type == "class"]

    def get_imports(self) -> List[Symbol]:
        """Get all import symbols."""
        return [s for s in self._all_symbols if s.type == "import"]

    def get_interfaces(self) -> List[Symbol]:
        """Get all interface symbols (TypeScript)."""
        return [s for s in self._all_symbols if s.type == "interface"]

    def get_types(self) -> List[Symbol]:
        """Get all type alias symbols (TypeScript)."""
        return [s for s in self._all_symbols if s.type == "type"]

    def search_by_prefix(self, prefix: str) -> List[Symbol]:
        """Find all symbols whose name starts with prefix."""
        results = []
        for symbol in self._all_symbols:
            if symbol.name.startswith(prefix):
                results.append(symbol)
        return results

    def get_methods_of_class(self, class_name: str) -> List[Symbol]:
        """Get all methods of a class."""
        return [
            s
            for s in self._all_symbols
            if s.type == "function" and s.parent == class_name
        ]

    def get_duplicates(self) -> Dict[str, List[Symbol]]:
        """Get all names that have multiple definitions."""
        duplicates = {}
        for name, symbols in self._by_name.items():
            if len(symbols) > 1:
                duplicates[name] = symbols
        return duplicates

    def __len__(self) -> int:
        """Return total number of symbols."""
        return len(self._all_symbols)

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"SymbolIndex({len(self._all_symbols)} symbols, "
            f"{len(self._by_file)} files, "
            f"{len(self._by_name)} unique names)"
        )
