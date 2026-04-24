"""Local staging utilities for folder ingestion payloads."""

from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path
from typing import Dict, Tuple

from coderag.core.settings import SETTINGS


REPO_ROOT = Path(__file__).resolve().parents[3]


def _staging_root() -> Path:
    """Resolve the shared staging root from runtime settings."""
    return SETTINGS.data_dir / "ingestion_staging"


def _resolve_source_path(local_path: str) -> Path:
    """Resolve user-selected path against repository root when relative."""
    candidate = Path(local_path).expanduser()
    if candidate.is_absolute():
        return candidate
    return (REPO_ROOT / candidate).resolve(strict=False)


def _ensure_not_inside_staging(source_path: Path) -> None:
    """Prevent recursive copy loops when users pick staging folders."""
    staging_root = _staging_root().resolve(strict=False)
    resolved_source = source_path.resolve(strict=False)
    try:
        resolved_source.relative_to(staging_root)
    except ValueError:
        return
    raise ValueError(
        "Selected folder is inside ingestion staging path; "
        "choose another folder."
    )


def _stage_target_name(source_path: Path) -> str:
    """Build unique destination folder name for each ingestion request."""
    digest_seed = f"{source_path}:{time.time_ns()}"
    digest = hashlib.sha1(digest_seed.encode("utf-8")).hexdigest()[:10]
    base_name = source_path.name.strip() or "source"
    return f"{base_name}_{digest}"


def _cleanup_old_staging_dirs(limit: int = 20) -> None:
    """Keep staging storage bounded to avoid unbounded disk growth."""
    staging_root = _staging_root()
    if not staging_root.exists() or limit < 1:
        return
    candidates = [
        item
        for item in staging_root.iterdir()
        if item.is_dir()
    ]
    if len(candidates) <= limit:
        return

    candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    for stale in candidates[limit:]:
        shutil.rmtree(stale, ignore_errors=True)


def stage_folder_source(local_path: str) -> Tuple[str, Dict[str, str]]:
    """Copy selected folder into repository staging and return relative path."""
    source_text = local_path.strip()
    if not source_text:
        raise ValueError("Local folder path is required for folder ingestion.")

    source_path = _resolve_source_path(source_text)
    if not source_path.exists():
        raise FileNotFoundError(f"Selected folder does not exist: {source_path}")
    if not source_path.is_dir():
        raise NotADirectoryError(f"Selected path is not a folder: {source_path}")

    _ensure_not_inside_staging(source_path)
    staging_root = _staging_root()
    staging_root.mkdir(parents=True, exist_ok=True)

    target = staging_root / _stage_target_name(source_path)
    shutil.copytree(source_path, target)
    _cleanup_old_staging_dirs(limit=20)

    runtime_local_path = str(target)
    metadata = {
        "source_path": str(source_path),
        "staged_path": str(target),
        "runtime_local_path": runtime_local_path,
    }
    return runtime_local_path, metadata