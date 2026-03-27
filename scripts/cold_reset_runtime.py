"""Apply destructive storage reset used by scripts/cold_reset.ps1.

This script removes local persisted artifacts and clears Neo4j graph edges.
It is intentionally separate from PowerShell orchestration to avoid quoting
issues with inline Python execution.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def _to_abs(repo_root: Path, value: Path) -> Path:
    """Return absolute path using repository root as base when needed."""
    if value.is_absolute():
        return value
    return (repo_root / value).resolve()


def main() -> int:
    """Run cold reset and print a machine-readable summary."""
    if len(sys.argv) < 2:
        print("Missing repository root path.", file=sys.stderr)
        return 2

    repo_root = Path(sys.argv[1]).resolve()
    src_dir = repo_root / "src"
    if src_dir.exists() and str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    from coderag.core.graph_store import GraphStore
    from coderag.core.settings import SETTINGS

    data_dir = _to_abs(repo_root, Path(SETTINGS.data_dir))
    chroma_dir = _to_abs(repo_root, Path(SETTINGS.chroma_persist_dir))
    metadata_db = data_dir / "metadata.db"

    if chroma_dir.exists():
        shutil.rmtree(chroma_dir)
    chroma_dir.mkdir(parents=True, exist_ok=True)

    if metadata_db.exists():
        metadata_db.unlink()

    neo4j_deleted_edges = None
    neo4j_error = None
    try:
        graph_store = GraphStore()
        neo4j_deleted_edges = graph_store.clear_all_edges()
        graph_store.close()
    except Exception as exc:  # pragma: no cover - depends on runtime
        neo4j_error = str(exc)

    print(
        json.dumps(
            {
                "chroma_dir": str(chroma_dir),
                "metadata_db": str(metadata_db),
                "neo4j_deleted_edges": neo4j_deleted_edges,
                "neo4j_error": neo4j_error,
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())