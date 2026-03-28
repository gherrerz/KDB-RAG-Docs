"""Document loading orchestration for supported source types."""

from __future__ import annotations

import difflib
import hashlib
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from coderag.core.models import DocumentRecord, SourceConfig
from coderag.ingestion.confluence_client import ConfluenceClient
from coderag.ingestion.repo_scanner import scan_folder_with_diagnostics
from coderag.parsers.generic_parser import parse_by_extension


def _source_id_from_path(path: str) -> str:
    digest = hashlib.sha1(path.encode("utf-8")).hexdigest()
    return digest[:12]


def _emit_progress(
    callback: Callable[[str, Dict[str, object]], None] | None,
    event: str,
    payload: Dict[str, object],
) -> None:
    """Emit loader progress events when callback is provided."""
    if callback is None:
        return
    callback(event, payload)


def _normalize_path_token(value: str) -> str:
    """Normalize path text for accent-insensitive suggestion matching."""
    normalized = unicodedata.normalize("NFKD", value)
    stripped = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return stripped.casefold().strip()


def _suggest_nearby_paths(path: Path, limit: int = 3) -> List[str]:
    """Suggest similar sibling folders when configured path is invalid."""
    parent = path.parent
    target_name = path.name
    if not target_name or not parent.exists() or not parent.is_dir():
        return []

    siblings = [
        entry
        for entry in parent.iterdir()
        if entry.is_dir()
    ]
    if not siblings:
        return []

    normalized_target = _normalize_path_token(target_name)
    sibling_by_name = {
        _normalize_path_token(entry.name): entry
        for entry in siblings
    }
    close_names = difflib.get_close_matches(
        normalized_target,
        list(sibling_by_name.keys()),
        n=max(1, limit),
        cutoff=0.55,
    )
    suggestions = [str(sibling_by_name[name]) for name in close_names]

    if suggestions:
        return suggestions

    contains_matches = [
        str(entry)
        for entry in siblings
        if normalized_target in _normalize_path_token(entry.name)
        or _normalize_path_token(entry.name) in normalized_target
    ]
    return contains_matches[:limit]


def load_documents(
    source: SourceConfig,
    progress_callback: Callable[[str, Dict[str, object]], None] | None = None,
) -> Tuple[List[DocumentRecord], Dict[str, object]]:
    """Load and normalize documents from a configured source."""
    if source.source_type == "confluence" and source.base_url and source.token:
        client = ConfluenceClient(base_url=source.base_url, token=source.token)
        pages = client.fetch_pages(source.filters)
        source_id = _source_id_from_path(source.base_url)
        documents = [
            DocumentRecord(
                document_id=f"{source_id}-{idx}",
                source_id=source_id,
                title=page.get("title", f"page-{idx}"),
                content=page.get("content", ""),
                path_or_url=page.get("url", ""),
                content_type="confluence-page",
                updated_at=datetime.now(UTC),
                metadata={"origin": "confluence"},
            )
            for idx, page in enumerate(pages)
        ]
        _emit_progress(
            progress_callback,
            "confluence_fetch_completed",
            {
                "pages": len(pages),
                "documents": len(documents),
            },
        )
        return documents, {
            "source_type": "confluence",
            "discovered_files": len(pages),
            "parsed_documents": len(documents),
            "skipped_empty": 0,
            "extensions": {"confluence-page": len(documents)},
        }

    if not source.local_path:
        return [], {
            "source_type": "folder",
            "failure_reason": "path_not_set",
            "path_exists": False,
            "path_is_dir": False,
            "discovered_files": 0,
            "total_files_seen": 0,
            "parsed_documents": 0,
            "skipped_empty": 0,
            "extensions": {},
            "scan_error_count": 0,
            "scan_error_examples": [],
            "suggested_paths": [],
        }

    root = Path(source.local_path).expanduser()
    resolved_root = root.resolve(strict=False)
    source_id = _source_id_from_path(str(resolved_root))
    documents: List[DocumentRecord] = []
    discovered_files, scan_stats = scan_folder_with_diagnostics(resolved_root)
    total_files = len(discovered_files)
    skipped_empty = 0
    extensions: Dict[str, int] = {}

    path_exists = bool(scan_stats.get("path_exists", False))
    path_is_dir = bool(scan_stats.get("path_is_dir", False))
    scan_error_count = int(scan_stats.get("scan_error_count", 0))
    scan_error_examples = list(scan_stats.get("scan_error_examples", []))
    total_files_seen = int(scan_stats.get("total_files_seen", 0))
    failure_reason = ""
    if not path_exists:
        failure_reason = "path_not_found"
    elif not path_is_dir:
        failure_reason = "path_not_directory"
    elif total_files == 0:
        failure_reason = "no_supported_documents"

    suggestions = _suggest_nearby_paths(resolved_root)

    _emit_progress(
        progress_callback,
        "folder_scan_completed",
        {
            "path": str(resolved_root),
            "discovered_files": total_files,
            "total_files_seen": total_files_seen,
            "path_exists": path_exists,
            "path_is_dir": path_is_dir,
            "scan_error_count": scan_error_count,
        },
    )

    for index, file_path in enumerate(discovered_files, start=1):
        text = parse_by_extension(file_path)
        if not text.strip():
            skipped_empty += 1
            continue
        document_id = hashlib.sha1(
            str(file_path.resolve()).encode("utf-8")
        ).hexdigest()[:16]
        extension = file_path.suffix.lower().lstrip(".")
        extensions[extension] = extensions.get(extension, 0) + 1
        documents.append(
            DocumentRecord(
                document_id=document_id,
                source_id=source_id,
                title=file_path.stem,
                content=text,
                path_or_url=str(file_path),
                content_type=extension,
                updated_at=datetime.now(UTC),
                metadata={"origin": "folder"},
            )
        )

        if index == 1 or index % 5 == 0 or index == total_files:
            _emit_progress(
                progress_callback,
                "folder_parse_progress",
                {
                    "processed_files": index,
                    "total_files": total_files,
                    "parsed_documents": len(documents),
                    "skipped_empty": skipped_empty,
                },
            )

    _emit_progress(
        progress_callback,
        "folder_parse_completed",
        {
            "parsed_documents": len(documents),
            "skipped_empty": skipped_empty,
            "extensions": extensions,
            "failure_reason": failure_reason,
        },
    )

    return documents, {
        "source_type": "folder",
        "source_path": str(resolved_root),
        "failure_reason": failure_reason,
        "path_exists": path_exists,
        "path_is_dir": path_is_dir,
        "discovered_files": total_files,
        "total_files_seen": total_files_seen,
        "parsed_documents": len(documents),
        "skipped_empty": skipped_empty,
        "extensions": extensions,
        "scan_error_count": scan_error_count,
        "scan_error_examples": scan_error_examples,
        "suggested_paths": suggestions,
    }
