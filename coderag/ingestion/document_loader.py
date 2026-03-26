"""Document loading orchestration for supported source types."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import List

from coderag.core.models import DocumentRecord, SourceConfig
from coderag.ingestion.confluence_client import ConfluenceClient
from coderag.ingestion.repo_scanner import scan_folder
from coderag.parsers.generic_parser import parse_by_extension


def _source_id_from_path(path: str) -> str:
    digest = hashlib.sha1(path.encode("utf-8")).hexdigest()
    return digest[:12]


def load_documents(source: SourceConfig) -> List[DocumentRecord]:
    """Load and normalize documents from a configured source."""
    if source.source_type == "confluence" and source.base_url and source.token:
        client = ConfluenceClient(base_url=source.base_url, token=source.token)
        pages = client.fetch_pages(source.filters)
        source_id = _source_id_from_path(source.base_url)
        return [
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

    if not source.local_path:
        return []

    root = Path(source.local_path)
    source_id = _source_id_from_path(str(root.resolve()))
    documents: List[DocumentRecord] = []

    for file_path in scan_folder(root):
        text = parse_by_extension(file_path)
        if not text.strip():
            continue
        document_id = hashlib.sha1(
            str(file_path.resolve()).encode("utf-8")
        ).hexdigest()[:16]
        documents.append(
            DocumentRecord(
                document_id=document_id,
                source_id=source_id,
                title=file_path.stem,
                content=text,
                path_or_url=str(file_path),
                content_type=file_path.suffix.lower().lstrip("."),
                updated_at=datetime.now(UTC),
                metadata={"origin": "folder"},
            )
        )

    return documents
