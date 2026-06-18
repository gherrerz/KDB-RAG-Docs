"""Utilities to stage uploaded files for ingestion endpoints."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from fastapi import UploadFile

from coderag.core.models import IngestionRequest, SourceConfig
from coderag.ingestion.repo_scanner import ALLOWED_EXTENSIONS

_DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


class UploadIngestionError(ValueError):
    """Domain error raised when upload ingestion payload is invalid."""


@dataclass(frozen=True)
class StagedUploadFile:
    """One uploaded file captured for staging and artifact persistence."""

    ordinal: int
    original_filename: str
    staged_filename: str
    media_type: str | None
    size_bytes: int
    content_hash: str
    payload: bytes


@dataclass(frozen=True)
class StagedUploadBatch:
    """One staged upload batch plus the captured per-file payloads."""

    staged_dir: Path
    files: list[StagedUploadFile]


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

    def stage_uploads_batch(self, files: list[UploadFile]) -> StagedUploadBatch:
        """Persist uploaded files into one isolated temporary directory."""
        return self.materialize_batch(self.collect_uploads(files))

    def materialize_batch(
        self,
        captured_files: list[StagedUploadFile],
    ) -> StagedUploadBatch:
        """Write already-captured payloads into one isolated temporary dir."""
        upload_dir = self.base_dir / uuid.uuid4().hex
        upload_dir.mkdir(parents=True, exist_ok=False)
        try:
            for staged_file in captured_files:
                destination = upload_dir / staged_file.staged_filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(staged_file.payload)
        except Exception:
            shutil.rmtree(upload_dir, ignore_errors=True)
            raise

        return StagedUploadBatch(staged_dir=upload_dir, files=captured_files)

    def collect_uploads(self, files: list[UploadFile]) -> list[StagedUploadFile]:
        """Read multipart uploaded files into memory for staging/artifacts."""
        if not files:
            raise UploadIngestionError(
                "Upload ingestion requires at least one file."
            )

        used_names: set[str] = set()
        captured_files: list[StagedUploadFile] = []
        for ordinal, upload in enumerate(files):
            raw_name = upload.filename or "upload.txt"
            payload = upload.file.read(self.max_upload_bytes + 1)
            captured_files.append(
                self._capture_payload(
                    ordinal=ordinal,
                    raw_name=raw_name,
                    payload=payload,
                    media_type=upload.content_type,
                    used_names=used_names,
                )
            )

        return captured_files

    def collect_payloads(
        self,
        items: list[tuple[str, bytes, str | None]],
    ) -> list[StagedUploadFile]:
        """Capture already-decoded ``(filename, bytes, media_type)`` items.

        Runs the same sanitization, dedup, extension and size validation as
        :meth:`collect_uploads`, but over content already in memory (for
        JSON/base64 ingestion flows that do not use multipart ``UploadFile``).
        """
        if not items:
            raise UploadIngestionError(
                "Upload ingestion requires at least one file."
            )

        used_names: set[str] = set()
        captured_files: list[StagedUploadFile] = []
        for ordinal, (raw_name, payload, media_type) in enumerate(items):
            captured_files.append(
                self._capture_payload(
                    ordinal=ordinal,
                    raw_name=raw_name or "upload.txt",
                    payload=payload,
                    media_type=media_type,
                    used_names=used_names,
                )
            )

        return captured_files

    def _capture_payload(
        self,
        ordinal: int,
        raw_name: str,
        payload: bytes,
        media_type: str | None,
        used_names: set[str],
    ) -> StagedUploadFile:
        """Validate one in-memory payload and build its staged descriptor."""
        safe_base_name = self._sanitize_filename(raw_name)
        safe_name = self._dedupe_filename(safe_base_name, used_names)
        self._validate_extension(safe_name)

        if len(payload) > self.max_upload_bytes:
            raise UploadIngestionError(
                "Uploaded file exceeds maximum size "
                f"({self.max_upload_bytes} bytes): {safe_name}"
            )

        return StagedUploadFile(
            ordinal=ordinal,
            original_filename=raw_name,
            staged_filename=safe_name,
            media_type=media_type,
            size_bytes=len(payload),
            content_hash=hashlib.sha256(payload).hexdigest(),
            payload=payload,
        )

    def parse_filters(self, filters_raw: str | None) -> dict[str, Any]:
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

    def parse_tags(self, tags_raw: str | None) -> list[str]:
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
        staged_dir: Path | None,
        source_type: str,
        filters: dict[str, Any],
        tags: list[str] | None = None,
        artifact_id: str | None = None,
    ) -> IngestionRequest:
        """Build canonical ingestion request from staged upload content."""
        normalized_source_type = (source_type or "folder").strip().lower()
        if normalized_source_type != "folder":
            raise UploadIngestionError(
                "Upload endpoint currently supports source_type='folder' only."
            )

        source = SourceConfig(
            source_type="folder",
            local_path=(str(staged_dir) if staged_dir is not None else None),
            logical_root="",
            artifact_id=artifact_id,
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
        normalized = PurePosixPath(filename)
        stem = normalized.stem
        suffix = normalized.suffix
        parent = str(normalized.parent)
        candidate = filename
        counter = 2
        while candidate.casefold() in used_names:
            if parent and parent != ".":
                candidate = f"{parent}/{stem}_{counter}{suffix}"
            else:
                candidate = f"{stem}_{counter}{suffix}"
            counter += 1
        used_names.add(candidate.casefold())
        return candidate

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Normalize uploaded logical path and remove unsafe characters."""
        normalized = str(filename or "").replace("\\", "/").strip()
        raw_parts = [part.strip() for part in normalized.split("/")]
        safe_parts: list[str] = []

        for part in raw_parts:
            if part in {"", ".", ".."}:
                continue
            sanitized = _SAFE_FILENAME_PATTERN.sub("_", part)
            if sanitized in {"", ".", ".."}:
                continue
            safe_parts.append(sanitized)

        if not safe_parts:
            return "upload.txt"
        return "/".join(safe_parts)

    @staticmethod
    def _normalize_tags(raw_tags: list[object]) -> list[str]:
        """Return stable, deduplicated tags suitable for requests."""
        normalized: list[str] = []
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
