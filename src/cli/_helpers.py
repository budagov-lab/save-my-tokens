"""Shared state and utilities for SMT CLI sub-modules."""

import functools
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from loguru import logger

# Repo root: src/cli/_helpers.py → src/cli/ → src/ → repo root
SMT_DIR = Path(__file__).parent.parent.parent.resolve()

if str(SMT_DIR) not in sys.path:
    sys.path.insert(0, str(SMT_DIR))

from cli_utils import Colors

_C = Colors

# ---------------------------------------------------------------------------
# Global state (connection pooling)
# ---------------------------------------------------------------------------

_neo4j_client: Optional[Any] = None
_validation_cache: Optional[Any] = None
_project_path_cache: Optional[Path] = None
_embedding_service_cache: Optional[Any] = None
_global_config_cache: Optional[dict] = None

# ---------------------------------------------------------------------------
# Global user config  (~/.smt/config.json)
# ---------------------------------------------------------------------------

_GLOBAL_SMT_DIR = Path.home() / '.smt'
_GLOBAL_CONFIG_FILE = _GLOBAL_SMT_DIR / 'config.json'

_GLOBAL_CONFIG_SCHEMA: dict = {
    'models_dir':    {'type': 'path',  'default': None,  'desc': 'Shared model cache directory (e.g. ~/.smt/models)'},
    'default_depth': {'type': 'int',   'default': None,  'desc': 'Default query depth, 1–10'},
    'compact':       {'type': 'bool',  'default': False, 'desc': 'Compact output format by default'},
    'brief':         {'type': 'bool',  'default': False, 'desc': 'Suppress docstrings by default'},
}


def _read_global_config() -> dict:
    """Read ~/.smt/config.json. Cached per process; returns {} on any error."""
    global _global_config_cache
    if _global_config_cache is not None:
        return _global_config_cache
    try:
        if _GLOBAL_CONFIG_FILE.exists():
            with open(_GLOBAL_CONFIG_FILE, 'r', encoding='utf-8') as f:
                _global_config_cache = json.load(f)
                return _global_config_cache
    except Exception:
        pass
    _global_config_cache = {}
    return _global_config_cache


def _write_global_config(key: str, value: Any) -> None:
    """Persist one key to ~/.smt/config.json, creating the file if needed."""
    global _global_config_cache
    _GLOBAL_SMT_DIR.mkdir(parents=True, exist_ok=True)
    cfg = dict(_read_global_config())
    if value is None:
        cfg.pop(key, None)
    else:
        cfg[key] = value
    with open(_GLOBAL_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)
    _global_config_cache = cfg


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _ok(msg: str) -> None:
    print(f"{Colors.GREEN}[OK]{Colors.RESET}   {msg}")


def _fail(msg: str) -> None:
    print(f"{Colors.RED}[FAIL]{Colors.RESET} {msg}")


def _warn(msg: str) -> None:
    print(f"{Colors.YELLOW}[WARN]{Colors.RESET} {msg}")


# ---------------------------------------------------------------------------
# Project identity
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=8)
def _get_project_id(project_root: Path) -> str:
    """Derive a stable 12-char project ID from the project root path."""
    return hashlib.sha256(str(project_root.resolve()).encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Neo4j connection pooling
# ---------------------------------------------------------------------------

def _get_neo4j_client(project_id: str = "") -> Any:
    """Get or create singleton Neo4j client (connection pooling).

    Re-creates the client if project_id has changed so queries never run
    against the wrong project's data.
    """
    global _neo4j_client
    if _neo4j_client is None or _neo4j_client.project_id != project_id:
        _close_neo4j_client()
        from src.config import settings
        from src.graph.neo4j_client import Neo4jClient
        _neo4j_client = Neo4jClient(
            settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD,
            project_id=project_id,
        )
    return _neo4j_client


def _close_neo4j_client() -> None:
    """Close the global client on exit."""
    global _neo4j_client
    if _neo4j_client:
        _neo4j_client.driver.close()
        _neo4j_client = None


# ---------------------------------------------------------------------------
# SMTQueryEngine (for --json output)
# ---------------------------------------------------------------------------

def _get_engine(project_path: Optional[Path] = None) -> Any:
    """Return an SMTQueryEngine scoped to the current project."""
    from src.agents.query_engine import SMTQueryEngine
    from src.config import settings
    path = (project_path or _resolve_project_path()).resolve()
    project_id = _get_project_id(path)
    cache_dir = path / '.smt' / 'embeddings'
    return SMTQueryEngine(
        neo4j_uri=settings.NEO4J_URI,
        neo4j_user=settings.NEO4J_USER,
        neo4j_password=settings.NEO4J_PASSWORD,
        embeddings_cache_dir=cache_dir,
        project_id=project_id,
    )


def _get_validation(repo_path: Path) -> Any:
    """Get or create cached validation result."""
    global _validation_cache
    if _validation_cache is None:
        from src.graph.validator import validate_graph
        project_id = _get_project_id(repo_path)
        client = _get_neo4j_client(project_id)
        _validation_cache = validate_graph(client, repo_path)
    return _validation_cache


def _get_services() -> Any:
    """Lazy-import heavy services so CLI starts fast for docker/status commands."""
    from src.config import settings
    from src.embeddings.embedding_service import EmbeddingService
    from src.graph.graph_builder import GraphBuilder
    from src.graph.neo4j_client import Neo4jClient
    from src.incremental.updater import IncrementalSymbolUpdater
    from src.parsers.symbol_index import SymbolIndex
    return settings, Neo4jClient, GraphBuilder, SymbolIndex, EmbeddingService, IncrementalSymbolUpdater


# ---------------------------------------------------------------------------
# Project path resolution
# ---------------------------------------------------------------------------

def _resolve_project_path() -> Path:
    """Walk up from cwd looking for .smt/config.json (like git). Falls back to cwd."""
    global _project_path_cache
    if _project_path_cache is not None:
        return _project_path_cache
    search = Path.cwd()
    for candidate in [search, *search.parents]:
        cfg = candidate / '.smt' / 'config.json'
        if cfg.exists():
            _project_path_cache = candidate.resolve()
            return _project_path_cache
    _project_path_cache = search
    return _project_path_cache


def _get_embedding_service(cache_dir: Path) -> Any:
    """Get or create singleton EmbeddingService (model loaded once per process)."""
    global _embedding_service_cache
    if _embedding_service_cache is None:
        import os
        from src.parsers.symbol_index import SymbolIndex

        # sentence_transformers sets up tqdm at import time, so TQDM_DISABLE must be
        # set BEFORE the import to suppress the "Loading weights" progress bar.
        _global_models = _read_global_config().get('models_dir')
        _models_dir = Path(_global_models).expanduser().resolve() if _global_models else cache_dir / "models"
        _model_cached = _models_dir.exists() and any(_models_dir.glob("models--*"))
        _prev_tqdm = os.environ.get("TQDM_DISABLE")
        if _model_cached:
            os.environ["TQDM_DISABLE"] = "1"
        try:
            from src.embeddings.embedding_service import EmbeddingService
            _embedding_service_cache = EmbeddingService(SymbolIndex(), cache_dir=cache_dir, models_dir=_models_dir)
        finally:
            if _prev_tqdm is None:
                os.environ.pop("TQDM_DISABLE", None)
            else:
                os.environ["TQDM_DISABLE"] = _prev_tqdm
    return _embedding_service_cache


def _get_default_depth(fallback: int) -> int:
    """Return default query depth. Priority: project config > global config > fallback."""
    try:
        cfg_file = _resolve_project_path() / '.smt' / 'config.json'
        if cfg_file.exists():
            with open(cfg_file, 'r', encoding='utf-8') as f:
                val = json.load(f).get('default_depth')
            if isinstance(val, int) and 1 <= val <= 10:
                return val
    except Exception:
        pass
    val = _read_global_config().get('default_depth')
    if isinstance(val, int) and 1 <= val <= 10:
        return val
    return fallback


def _get_default_compact() -> bool:
    """Return global compact preference (CLI flag always overrides)."""
    return bool(_read_global_config().get('compact', False))


def _get_default_brief() -> bool:
    """Return global brief preference (CLI flag always overrides)."""
    return bool(_read_global_config().get('brief', False))


# ---------------------------------------------------------------------------
# .smtignore
# ---------------------------------------------------------------------------

_SMTIGNORE_TEMPLATE = """\
# .smtignore — files and directories excluded from smt build and smt watch
# Syntax:
#   simple name  →  matches any path component  (e.g. vendor)
#   path/pattern →  matched against relative path from project root
#   *.glob       →  fnmatch glob against filename
#
# Default skip dirs are always applied (node_modules, .venv, __pycache__, …)
# Add project-specific overrides below:

# tests/fixtures
# vendor
# *.generated.py
"""


def _ensure_smtignore(project_root: Path) -> None:
    """Create a .smtignore in project_root if one doesn't exist yet."""
    smtignore = project_root / '.smtignore'
    if not smtignore.exists():
        smtignore.write_text(_SMTIGNORE_TEMPLATE, encoding='utf-8')
        print(f"  .smtignore created in {project_root}")


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _require_git(path: Path) -> bool:
    """Check that path is a git repository. Prints error if not."""
    if not (path / '.git').exists():
        print(f"ERROR: {path} is not a git repository.")
        print(f"  Run: smt setup --dir {path}")
        return False
    return True


def _git_initial_commit(target_dir: Path) -> None:
    """Anchor current project state in git history."""
    def _git_config_missing(key: str) -> bool:
        result = subprocess.run(
            ['git', 'config', key], cwd=target_dir, capture_output=True
        )
        return result.returncode != 0 or not result.stdout.strip()

    if _git_config_missing('user.name'):
        subprocess.run(['git', 'config', 'user.name', 'SMT'], cwd=target_dir, capture_output=True)
    if _git_config_missing('user.email'):
        subprocess.run(['git', 'config', 'user.email', 'smt@local'], cwd=target_dir, capture_output=True)

    result = subprocess.run(
        ['git', 'log', '--oneline', '-1'],
        cwd=target_dir, capture_output=True
    )
    has_commits = result.returncode == 0 and result.stdout.strip()

    if has_commits:
        subprocess.run(['git', 'add', '.claude/'], cwd=target_dir, capture_output=True)
        staged = subprocess.run(
            ['git', 'diff', '--cached', '--name-only'],
            cwd=target_dir, capture_output=True
        )
        if staged.stdout.strip():
            subprocess.run(
                ['git', 'commit', '-m', 'chore: Initialize SMT graph index'],
                cwd=target_dir, capture_output=True
            )
    else:
        subprocess.run(['git', 'add', '.'], cwd=target_dir, capture_output=True)
        subprocess.run(
            ['git', 'commit', '-m', 'Initial: Build graph index'],
            cwd=target_dir, capture_output=True
        )

    print("  git commit             [OK] — Graph state anchored in git history")
