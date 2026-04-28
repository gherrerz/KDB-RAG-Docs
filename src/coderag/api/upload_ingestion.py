"""Utilities to stage uploaded files for ingestion endpoints."""

from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import UploadFile

from coderag.core.models import IngestionRequest, SourceConfig
from coderag.ingestion.repo_scanner import ALLOWED_EXTENSIONS

_DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


class UploadIngestionError(ValueError):
    """Domain error raised when upload ingestion payload is invalid."""


class UploadIngestionAdapter:
    """Stage uploaded files and build compatible ingestion requests."""

    def __init__(
        self,
        base_dir: Path,
        max_upload_bytes: int = _DEFAULT_MAX_UPLOAD_BYTES,
    ) -> None:
        """Initialize adapter with storage location and upload size limit."""
        self.base_dir = base_dir
        self.max_upload_bytes = max_upload_bytes

    def stage_upload(self, file: UploadFile) -> Path:
        """Persist uploaded file into an isolated temporary directory."""
        raw_name = file.filename or "upload.txt"
        safe_name = self._sanitize_filename(raw_name)
        extension = Path(safe_name).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
            raise UploadIngestionError(
                "Unsupported file extension for ingestion upload. "
                f"Allowed: {allowed}"
            )

        upload_dir = self.base_dir / uuid.uuid4().hex
        upload_dir.mkdir(parents=True, exist_ok=False)
        destination = upload_dir / safe_name

        payload = file.file.read(self.max_upload_bytes + 1)
        if len(payload) > self.max_upload_bytes:
            raise UploadIngestionError(
                "Uploaded file exceeds maximum size "
                f"({self.max_upload_bytes} bytes)."
            )

        destination.write_bytes(payload)
        return upload_dir

    def parse_filters(self, filters_raw: str | None) -> Dict[str, Any]:
        """Parse optional JSON filters string from multipart form field."""
        if not filters_raw or not filters_raw.strip():
            return {}
        try:
            parsed = json.loads(filters_raw)
        except json.JSONDecodeError as exc:
            raise UploadIngestionError(
                "filters must be valid JSON object text."
            ) from exc

        if not isinstance(parsed, dict):
            raise UploadIngestionError(
                "filters must decode to a JSON object."
            )
        return parsed

    def build_request(
        self,
        staged_dir: Path,
        source_type: str,
        filters: Dict[str, Any],
    ) -> IngestionRequest:
        """Build canonical ingestion request from staged upload content."""
        normalized_source_type = (source_type or "folder").strip().lower()
        if normalized_source_type != "folder":
            raise UploadIngestionError(
                "Upload endpoint currently supports source_type='folder' only."
            )

        source = SourceConfig(
            source_type="folder",
            local_path=str(staged_dir),
            filters=filters,
        )
        return IngestionRequest(source=source)

    def cleanup(self, staged_dir: Path) -> None:
        """Remove staged upload directory after ingestion completes."""
        shutil.rmtree(staged_dir, ignore_errors=True)

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Normalize filename and remove unsafe characters."""
        base_name = Path(filename).name.strip() or "upload.txt"
        sanitized = _SAFE_FILENAME_PATTERN.sub("_", base_name)
        if sanitized in {"", ".", ".."}:
            return "upload.txt"
        return sanitized
