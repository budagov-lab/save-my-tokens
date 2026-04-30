"""SMT watch command — file-system watcher for auto graph sync."""

from pathlib import Path
from typing import Optional

from src.cli._helpers import (
    _get_project_id,
    _get_services,
    _require_git,
    _resolve_project_path,
)
from src.incremental.node_manager import query_symbols_in_file


def cmd_watch(target_dir: Optional[str] = None, debounce: float = 2.0) -> int:
    """Watch source files and auto-sync the graph on changes.

    Monitors .py/.ts/.tsx/.js/.jsx files for changes. After a quiet period
    of `debounce` seconds, re-parses changed files and updates the graph.

    Note: CALLS edges are not rebuilt in watch mode — run `smt build` to
    refresh edge relationships after large refactors.
    """
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        print("ERROR: watchdog is not installed. Run:  pip install watchdog")
        return 1

    settings, Neo4jClient, _, SymbolIndex, EmbeddingService, IncrementalSymbolUpdater = _get_services()

    target_path = Path(target_dir).resolve() if target_dir else _resolve_project_path()
    if not _require_git(target_path):
        return 1

    project_id = _get_project_id(target_path)
    client = Neo4jClient(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD, project_id=project_id)
    index = SymbolIndex()
    cache_dir = target_path / '.smt' / 'embeddings'
    embedding_svc = EmbeddingService(index, cache_dir=cache_dir)
    updater = IncrementalSymbolUpdater(
        symbol_index=index,
        neo4j_client=client,
        embedding_service=embedding_svc,
        base_path=str(target_path),
    )

    import threading
    import time

    _SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java"}
    _pending: set = set()
    _timer: Optional[threading.Timer] = None
    _lock = threading.Lock()

    from src.graph.graph_builder import GraphBuilder as _GB
    from src.smtignore import SMTIgnore as _SMTIgnore
    _SKIP_DIRS = _GB._SKIP_DIRS
    _smtignore = _SMTIgnore(target_path)

    def _flush() -> None:
        with _lock:
            files = list(_pending)
            _pending.clear()
        if not files:
            return
        print(f"\n[watch] {len(files)} file(s) changed — syncing graph...", flush=True)
        updated = 0
        for abs_path in files:
            p = Path(abs_path)
            try:
                before = query_symbols_in_file(updater.neo4j, abs_path)
                if p.exists():
                    after = updater._parse_file(abs_path)
                else:
                    after = []
                delta = updater._compute_delta(abs_path, before, after)
                result = updater.apply_delta(delta)
                if result.success:
                    added = len(delta.added)
                    deleted = len(delta.deleted)
                    modified = len(delta.modified)
                    print(f"  {p.name}: +{added} -{deleted} ~{modified}", flush=True)
                    updated += 1
                else:
                    print(f"  {p.name}: FAILED — {result.error}", flush=True)
            except Exception as e:
                print(f"  {p.name}: ERROR — {e}", flush=True)
        if updated:
            print(f"[watch] Done. ({updated}/{len(files)} files updated)", flush=True)
        print("[watch] Note: CALLS edges not updated — run `smt build` to refresh call relationships.", flush=True)

    def _schedule_flush() -> None:
        nonlocal _timer
        if _timer:
            _timer.cancel()
        _timer = threading.Timer(debounce, _flush)
        _timer.daemon = True
        _timer.start()

    class _Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            if event.is_directory:
                return
            src = getattr(event, 'src_path', None)
            if not src:
                return
            p = Path(src)
            if p.suffix not in _SOURCE_EXTS:
                return
            if any(part in _SKIP_DIRS for part in p.parts):
                return
            if _smtignore.is_ignored(p):
                return
            with _lock:
                _pending.add(src)
            _schedule_flush()

    observer = Observer()
    observer.schedule(_Handler(), str(target_path), recursive=True)
    observer.start()
    print(f"[watch] Watching {target_path}  (debounce={debounce}s)  Ctrl+C to stop")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        client.driver.close()

    return 0
