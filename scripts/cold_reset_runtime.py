"""Apply destructive storage reset used by scripts/cold_reset.ps1.

This script removes local persisted artifacts, clears local staging mirror
folders, and clears Neo4j graph edges. It is intentionally separate from
PowerShell orchestration to avoid quoting issues with inline Python
execution.
"""

from __future__ import annotations

import json
import os
import stat
import shutil
import sys
from pathlib import Path


def _to_abs(repo_root: Path, value: Path) -> Path:
    """Return absolute path using repository root as base when needed."""
    if value.is_absolute():
        return value
    return (repo_root / value).resolve()


def _on_rmtree_error(func, path, _exc_info) -> None:
    """Best-effort handler for read-only files on Windows during delete."""
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    func(path)


def _reset_dir(path: Path, warnings: list[str]) -> None:
    """Delete and recreate directory, tolerating transient file locks."""
    if path.exists():
        try:
            shutil.rmtree(path, onexc=_on_rmtree_error)
        except PermissionError as exc:
            warnings.append(f"Could not fully remove '{path}': {exc}")
            # Best-effort cleanup to avoid aborting the full reset.
            for child in path.iterdir():
                try:
                    if child.is_dir():
                        shutil.rmtree(child, onexc=_on_rmtree_error)
                    else:
                        child.unlink()
                except Exception as child_exc:  # pragma: no cover - OS dependent
                    warnings.append(f"Could not remove '{child}': {child_exc}")
    path.mkdir(parents=True, exist_ok=True)


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
    staging_dir = data_dir / "ingestion_staging"
    warnings: list[str] = []

    _reset_dir(chroma_dir, warnings)

    if metadata_db.exists():
        try:
            metadata_db.unlink()
        except PermissionError as exc:  # pragma: no cover - OS dependent
            warnings.append(f"Could not remove '{metadata_db}': {exc}")

    _reset_dir(staging_dir, warnings)

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
                "staging_dir": str(staging_dir),
                "neo4j_deleted_edges": neo4j_deleted_edges,
                "neo4j_error": neo4j_error,
                "warnings": warnings,
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())