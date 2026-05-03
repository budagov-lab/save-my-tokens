"""SMT build command: parse source and persist graph to Neo4j."""

from pathlib import Path
from typing import Optional

from loguru import logger

from src.cli._helpers import (
    Colors,
    _C,
    _ensure_smtignore,
    _get_project_id,
    _get_services,
    _require_git,
    _resolve_project_path,
)


def cmd_build(check: bool = False, clear: bool = False, target_dir: Optional[str] = None, embeddings: bool = False) -> int:
    from src.cli.status import cmd_status

    settings, Neo4jClient, GraphBuilder, SymbolIndex, EmbeddingService, _ = _get_services()

    if check:
        return cmd_status()

    if target_dir:
        target_path = Path(target_dir).resolve()
    else:
        target_path = _resolve_project_path()

    if not _require_git(target_path):
        return 1

    _ensure_smtignore(target_path)

    src_dir = target_path

    print(f"{'Rebuilding' if clear else 'Building'} graph from {src_dir} ...")

    try:
        project_id = _get_project_id(target_path)
        client = Neo4jClient(settings.NEO4J_URI, settings.NEO4J_USER, settings.NEO4J_PASSWORD, project_id=project_id)

        if clear:
            print(f"{Colors.YELLOW}[WARN]{Colors.RESET} Clearing graph data for project: {target_path.name} [{project_id}]")
            client.clear_database()
            import shutil
            embeddings_dir = target_path / '.smt' / 'embeddings'
            if embeddings_dir.exists():
                shutil.rmtree(embeddings_dir)
                logger.info(f"Cleared embeddings cache: {embeddings_dir}")

        builder = GraphBuilder(str(src_dir), neo4j_client=client, project_id=project_id)
        builder.build(build_embeddings=False)

        if embeddings:
            try:
                from src.cli._helpers import _get_embedding_service
                from src.parsers.symbol import Symbol
                cache_dir = target_path / '.smt' / 'embeddings'
                cache_dir.mkdir(parents=True, exist_ok=True)
                svc = _get_embedding_service(cache_dir)
                with client.driver.session() as session:
                    rows = session.run(
                        "MATCH (n {project_id: $pid}) RETURN n, labels(n) as labels",
                        pid=project_id
                    ).data()
                for row in rows:
                    n = row['n']
                    labels = row['labels']
                    if not n.get('name'):
                        continue
                    svc.symbol_index.add(Symbol(
                        name=n.get('name', ''),
                        type=labels[0] if labels else 'Unknown',
                        file=n.get('file', ''),
                        line=n.get('line', 0),
                        column=n.get('column', 0),
                        docstring=n.get('docstring'),
                    ))
                print("Building semantic search index ...")
                svc.build_index()
                svc.save_index()
            except Exception as _emb_err:
                logger.warning(f"Embedding index build skipped: {_emb_err}")

        client.driver.close()
        print(f"Done. (project: {target_path.name} [{project_id}])")
        return cmd_status()
    except Exception as e:
        print(f"ERROR: {e}")
        return 1
