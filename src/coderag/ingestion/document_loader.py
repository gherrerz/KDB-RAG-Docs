"""Document loading orchestration for supported source types."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from coderag.core.models import DocumentRecord, SourceConfig
from coderag.ingestion.confluence_client import ConfluenceClient
from coderag.ingestion.repo_scanner import scan_folder
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
            "discovered_files": 0,
            "parsed_documents": 0,
            "skipped_empty": 0,
            "extensions": {},
        }

    root = Path(source.local_path)
    source_id = _source_id_from_path(str(root.resolve()))
    documents: List[DocumentRecord] = []
    discovered_files = scan_folder(root)
    total_files = len(discovered_files)
    skipped_empty = 0
    extensions: Dict[str, int] = {}

    _emit_progress(
        progress_callback,
        "folder_scan_completed",
        {
            "path": str(root),
            "discovered_files": total_files,
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
        },
    )

    return documents, {
        "source_type": "folder",
        "discovered_files": total_files,
        "parsed_documents": len(documents),
        "skipped_empty": skipped_empty,
        "extensions": extensions,
    }
