"""Utilities to stage uploaded files for ingestion endpoints."""

from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List

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

    def stage_uploads_batch(self, files: list[UploadFile]) -> Path:
        """Persist uploaded files into one isolated temporary directory."""
        if not files:
            raise UploadIngestionError(
                "Upload ingestion requires at least one file."
            )

        upload_dir = self.base_dir / uuid.uuid4().hex
        upload_dir.mkdir(parents=True, exist_ok=False)

        used_names: set[str] = set()
        try:
            for upload in files:
                raw_name = upload.filename or "upload.txt"
                safe_base_name = self._sanitize_filename(raw_name)
                safe_name = self._dedupe_filename(safe_base_name, used_names)
                self._validate_extension(safe_name)

                payload = upload.file.read(self.max_upload_bytes + 1)
                if len(payload) > self.max_upload_bytes:
                    raise UploadIngestionError(
                        "Uploaded file exceeds maximum size "
                        f"({self.max_upload_bytes} bytes): {safe_name}"
                    )

                destination = upload_dir / safe_name
                destination.write_bytes(payload)
        except Exception:
            shutil.rmtree(upload_dir, ignore_errors=True)
            raise

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

    def parse_tags(self, tags_raw: str | None) -> List[str]:
        """Parse optional tags form field as JSON array or CSV text."""
        if not tags_raw or not tags_raw.strip():
            return []

        stripped = tags_raw.strip()
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise UploadIngestionError(
                    "tags must be valid JSON array text or CSV text."
                ) from exc

            if not isinstance(parsed, list):
                raise UploadIngestionError(
                    "tags must decode to a JSON array."
                )
            return self._normalize_tags(parsed)

        return self._normalize_tags(stripped.split(","))

    def build_request(
        self,
        staged_dir: Path,
        source_type: str,
        filters: Dict[str, Any],
        tags: List[str] | None = None,
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
            tags=self._normalize_tags(tags or []),
        )
        return IngestionRequest(source=source)

    def cleanup(self, staged_dir: Path) -> None:
        """Remove staged upload directory after ingestion completes."""
        shutil.rmtree(staged_dir, ignore_errors=True)

    @staticmethod
    def _validate_extension(filename: str) -> None:
        """Ensure upload file extension is supported by ingestion scanner."""
        extension = Path(filename).suffix.lower()
        if extension in ALLOWED_EXTENSIONS:
            return
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise UploadIngestionError(
            "Unsupported file extension for ingestion upload. "
            f"Allowed: {allowed}"
        )

    @staticmethod
    def _dedupe_filename(filename: str, used_names: set[str]) -> str:
        """Avoid collisions inside one upload batch after sanitization."""
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        candidate = filename
        counter = 2
        while candidate.casefold() in used_names:
            candidate = f"{stem}_{counter}{suffix}"
            counter += 1
        used_names.add(candidate.casefold())
        return candidate

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Normalize filename and remove unsafe characters."""
        base_name = Path(filename).name.strip() or "upload.txt"
        sanitized = _SAFE_FILENAME_PATTERN.sub("_", base_name)
        if sanitized in {"", ".", ".."}:
            return "upload.txt"
        return sanitized

    @staticmethod
    def _normalize_tags(raw_tags: list[object]) -> List[str]:
        """Return stable, deduplicated tags suitable for requests."""
        normalized: List[str] = []
        seen: set[str] = set()
        for raw_tag in raw_tags:
            tag = str(raw_tag or "").strip()
            if not tag:
                continue
            tag_key = tag.casefold()
            if tag_key in seen:
                continue
            seen.add(tag_key)
            normalized.append(tag)
        return normalized
