"""Clean local runtime artifacts without using shell delete commands.

This script is intended for restricted environments where PowerShell
`Remove-Item` might be blocked by policy.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
from typing import Iterable


def _iter_pycache_dirs(root: Path, include_venv: bool) -> Iterable[Path]:
    """Yield __pycache__ directories under the workspace.

    By default `.venv` and `.git` are skipped to avoid deleting package caches.
    """
    skip = {".git"}
    if not include_venv:
        skip.add(".venv")

    for candidate in root.rglob("__pycache__"):
        if not candidate.is_dir():
            continue
        if any(part in skip for part in candidate.parts):
            continue
        yield candidate


def _safe_rmtree(path: Path) -> bool:
    """Delete a directory tree and return True when successful."""
    try:
        shutil.rmtree(path)
        return True
    except FileNotFoundError:
        return False


def clean_artifacts(
    root: Path,
    *,
    remove_metadata_db: bool,
    include_venv: bool,
) -> dict[str, int]:
    """Clean common local artifacts and return removal counters."""
    removed_pycache = 0

    for pycache in _iter_pycache_dirs(root, include_venv=include_venv):
        if _safe_rmtree(pycache):
            removed_pycache += 1

    removed_pytest_cache = 0
    pytest_cache = root / ".pytest_cache"
    if pytest_cache.exists() and _safe_rmtree(pytest_cache):
        removed_pytest_cache = 1

    removed_metadata_db = 0
    if remove_metadata_db:
        metadata_db = root / "storage" / "metadata.db"
        if metadata_db.exists():
            metadata_db.unlink()
            removed_metadata_db = 1

    return {
        "removed_pycache": removed_pycache,
        "removed_pytest_cache": removed_pytest_cache,
        "removed_metadata_db": removed_metadata_db,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser for cleanup options."""
    parser = argparse.ArgumentParser(
        description=(
            "Clean local runtime artifacts (__pycache__, .pytest_cache, "
            "optional storage/metadata.db)."
        )
    )
    parser.add_argument(
        "--remove-metadata-db",
        action="store_true",
        help="Also remove storage/metadata.db.",
    )
    parser.add_argument(
        "--include-venv",
        action="store_true",
        help="Also remove __pycache__ inside .venv.",
    )
    return parser


def main() -> int:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    result = clean_artifacts(
        root,
        remove_metadata_db=args.remove_metadata_db,
        include_venv=args.include_venv,
    )

    print(
        "Cleanup completed:",
        f"pycache={result['removed_pycache']}",
        f"pytest_cache={result['removed_pytest_cache']}",
        f"metadata_db={result['removed_metadata_db']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
