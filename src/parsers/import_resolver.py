"""Resolve and normalize import statements across Python and TypeScript."""

from pathlib import Path
from typing import List, Optional


class ImportResolver:
    """Resolve relative and absolute imports to canonical paths."""

    def __init__(self, base_path: Optional[str] = None):
        """Initialize resolver with optional base path for relative imports.

        Args:
            base_path: Root directory for resolving relative imports
        """
        self.base_path = Path(base_path) if base_path else Path.cwd()

    def resolve_python_import(
        self,
        import_path: str,
        from_file: str
    ) -> str:
        """Resolve Python import to absolute module path.

        Args:
            import_path: Import statement (e.g., "os", "typing.Dict", "../utils")
            from_file: File making the import (used for relative resolution)

        Returns:
            Canonical import path
        """
        # Handle relative imports (., .., ...)
        if import_path.startswith("."):
            return self._resolve_relative_import(import_path, from_file)

        # Absolute imports: return as-is
        return import_path

    def resolve_typescript_import(
        self,
        import_path: str,
        from_file: str
    ) -> str:
        """Resolve TypeScript/JavaScript import to canonical path.

        Args:
            import_path: Import path (e.g., "./utils", "@lib/helper", "lodash")
            from_file: File making the import

        Returns:
            Canonical import path
        """
        # Handle relative imports (./, ../)
        if import_path.startswith("."):
            return self._resolve_relative_import_ts(import_path, from_file)

        # Handle scoped packages (@scope/package)
        if import_path.startswith("@"):
            return import_path

        # Package imports: return as-is
        return import_path

    def _resolve_relative_import(self, rel_path: str, from_file: str) -> str:
        """Resolve relative Python import to absolute path.

        Example:
            from_file: "src/utils/helpers.py"
            rel_path: "..config"
            result: "src.config"
        """
        from_path = Path(from_file)

        # Count leading dots
        dot_count = len(rel_path) - len(rel_path.lstrip("."))
        module_part = rel_path[dot_count:]

        # Go up dot_count-1 levels from parent directory
        levels_up = dot_count - 1
        resolved = from_path.parent
        for _ in range(levels_up):
            resolved = resolved.parent

        # Add module part
        if module_part:
            resolved = resolved / module_part.replace(".", "/")

        # Convert to module notation
        return str(resolved).replace("/", ".").replace("\\", ".")

    def _resolve_relative_import_ts(self, rel_path: str, from_file: str) -> str:
        """Resolve relative TypeScript import to absolute path.

        Example:
            from_file: "src/utils/helpers.ts"
            rel_path: "../config"
            result: "src/config"
        """
        from_path = Path(from_file)

        # Remove leading ./
        if rel_path.startswith("./"):
            rel_path = rel_path[2:]
            # Resolve relative to same directory
            resolved = from_path.parent / rel_path
        else:
            # Handle ../
            resolved = from_path.parent
            while rel_path.startswith("../"):
                resolved = resolved.parent
                rel_path = rel_path[3:]
            resolved = resolved / rel_path

        # Normalize path
        resolved_str = str(resolved).replace("\\", "/")
        # Remove file extension if present
        if resolved_str.endswith((".ts", ".tsx", ".js", ".jsx")):
            resolved_str = ".".join(resolved_str.split(".")[:-1])

        return resolved_str

    @staticmethod
    def extract_import_names(import_statement: str) -> List[str]:
        """Extract imported names from import statement text.

        Handles:
        - import os -> ["os"]
        - import os, sys -> ["os", "sys"]
        - from typing import Dict, List -> ["Dict", "List"]
        - from . import config -> ["config"]
        - import * -> ["*"]

        Args:
            import_statement: Raw import statement text

        Returns:
            List of imported symbol names
        """
        statement = import_statement.strip()
        names = []

        if statement.startswith("from "):
            # from X import Y format
            if " import " in statement:
                import_part = statement.split(" import ", 1)[1]
                # Handle: Dict, List or * or config as name
                if import_part.strip() == "*":
                    names.append("*")
                else:
                    # Split by comma and clean up
                    for part in import_part.split(","):
                        name = part.strip().split(" as ")[-1].strip()
                        if name:
                            names.append(name)
        else:
            # import X format
            import_part = statement[6:].strip()  # Skip "import "
            for part in import_part.split(","):
                name = part.strip().split(" as ")[-1].strip()
                if name:
                    names.append(name)

        return names

    @staticmethod
    def is_stdlib_import(module_name: str) -> bool:
        """Check if import is from Python standard library.

        Args:
            module_name: Module name (e.g., "os", "sys", "typing")

        Returns:
            True if standard library module
        """
        # Common stdlib modules
        stdlib = {
            "abc", "aifc", "argparse", "array", "ast", "asyncio", "atexit",
            "audioop", "base64", "bdb", "binascii", "binhex", "bisect", "builtins",
            "bz2", "calendar", "cgi", "cgitb", "chunk", "cmath", "cmd", "code",
            "codecs", "codeop", "collections", "colorsys", "compileall", "concurrent",
            "configparser", "contextlib", "contextvars", "copy", "copyreg", "cProfile",
            "crypt", "csv", "ctypes", "curses", "dataclasses", "datetime", "dbm",
            "decimal", "difflib", "dis", "distutils", "doctest", "email", "encodings",
            "ensurepip", "enum", "errno", "faulthandler", "fcntl", "filecmp", "fileinput",
            "fnmatch", "fractions", "ftplib", "functools", "gc", "getopt", "getpass",
            "gettext", "glob", "graphlib", "grp", "gzip", "hashlib", "heapq", "hmac",
            "html", "http", "imaplib", "imghdr", "imp", "importlib", "inspect", "io",
            "ipaddress", "itertools", "json", "keyword", "lib2to3", "linecache",
            "locale", "logging", "lzma", "mailbox", "mailcap", "marshal", "math",
            "mimetypes", "mmap", "modulefinder", "msilib", "msvcrt", "multiprocessing",
            "netrc", "nis", "nntplib", "numbers", "operator", "optparse", "os",
            "ossaudiodev", "parser", "pathlib", "pdb", "pickle", "pickletools", "pipes",
            "pkgutil", "platform", "plistlib", "poplib", "posix", "posixpath", "pprint",
            "profile", "pstats", "pty", "pwd", "py_compile", "pyclbr", "pydoc",
            "queue", "quopri", "random", "readline", "reprlib", "resource", "rlcompleter",
            "runpy", "sched", "secrets", "select", "selectors", "shelve", "shlex",
            "shutil", "signal", "site", "sitecustomize", "smtpd", "smtplib", "sndhdr",
            "socket", "socketserver", "sqlite3", "ssl", "stat", "statistics", "string",
            "stringprep", "struct", "subprocess", "sunau", "symbol", "symtable", "sys",
            "sysconfig", "syslog", "tabnanny", "tarfile", "telnetlib", "tempfile",
            "termios", "test", "textwrap", "threading", "time", "timeit", "tkinter",
            "token", "tokenize", "tomllib", "trace", "traceback", "tracemalloc", "types",
            "typing", "typing_extensions", "unicodedata", "unittest", "urllib", "usercustomize",
            "uu", "uuid", "venv", "warnings", "wave", "weakref", "webbrowser", "wsgiref",
            "xdrlib", "xml", "xmlrpc", "zipapp", "zipfile", "zipimport", "zlib"
        }

        base_module = module_name.split(".")[0]
        return base_module in stdlib
