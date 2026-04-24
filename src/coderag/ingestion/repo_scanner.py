"""File discovery for folder-based ingestion."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Tuple

ALLOWED_EXTENSIONS = {
    ".md",
    ".txt",
    ".html",
    ".htm",
    ".pdf",
    ".docx",
    ".doc",
    ".pptx",
    ".xlsx",
}


def scan_folder(path: Path) -> List[Path]:
    """Return supported files recursively from a root path."""
    files, _stats = scan_folder_with_diagnostics(path)
    return files


def scan_folder_with_diagnostics(
    path: Path,
) -> Tuple[List[Path], Dict[str, object]]:
    """Return supported files plus scan diagnostics for robust failures."""
    path_exists = path.exists()
    path_is_dir = path.is_dir() if path_exists else False
    stats: Dict[str, object] = {
        "path": str(path),
        "path_exists": path_exists,
        "path_is_dir": path_is_dir,
        "total_files_seen": 0,
        "supported_files": 0,
        "scan_error_count": 0,
        "scan_error_examples": [],
    }
    if not path_exists or not path_is_dir:
        return [], stats

    discovered: List[Path] = []
    scan_errors: List[str] = []

    def _on_walk_error(exc: OSError) -> None:
        scan_errors.append(str(exc))

    for root, _dirs, files in os.walk(path, onerror=_on_walk_error):
        root_path = Path(root)
        for filename in files:
            stats["total_files_seen"] = int(stats["total_files_seen"]) + 1
            file_path = root_path / filename
            if file_path.suffix.lower() not in ALLOWED_EXTENSIONS:
                continue
            discovered.append(file_path)
            stats["supported_files"] = int(stats["supported_files"]) + 1

    discovered.sort(key=lambda item: item.as_posix().casefold())

    stats["scan_error_count"] = len(scan_errors)
    stats["scan_error_examples"] = scan_errors[:3]
    return discovered, stats
