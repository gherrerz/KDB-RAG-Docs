"""Presenter helpers for ingestion UI state and payload construction."""

from __future__ import annotations

import json


class IngestionPresenter:
    """Encapsula validaciones y payloads de ingesta para la vista Qt."""

    @staticmethod
    def safe_json(raw: str) -> dict:
        """Parse JSON object safely from user input field."""
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(value, dict):
            return value
        return {}

    @staticmethod
    def parse_tags(raw: str) -> list[str]:
        """Parse comma-separated tags preserving user case and order."""
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_tag in (raw or "").split(","):
            tag = raw_tag.strip()
            if not tag:
                continue
            tag_key = tag.casefold()
            if tag_key in seen:
                continue
            seen.add(tag_key)
            normalized.append(tag)
        return normalized

    def build_payload(
        self,
        *,
        source_type: str,
        local_path: str,
        base_url: str,
        token: str,
        filters_raw: str,
        tags_raw: str,
        ingestion_channel: str,
        execution_mode: str,
    ) -> dict[str, object]:
        """Create normalized ingestion payload consumed by backend callbacks."""
        return {
            "source": {
                "source_type": source_type.strip() or "folder",
                "local_path": local_path.strip() or None,
                "base_url": base_url.strip() or None,
                "token": token.strip() or None,
                "filters": self.safe_json(filters_raw.strip()),
                "tags": self.parse_tags(tags_raw),
            },
            "_ingestion_channel": ingestion_channel,
            "_ingestion_mode": execution_mode,
        }

    def validate_inputs(
        self,
        *,
        source_type: str,
        ingestion_channel: str,
        local_path: str,
        base_url: str,
        token: str,
        filters_raw: str,
    ) -> tuple[str | None, set[str]]:
        """Validate source fields and return message plus invalid field keys."""
        invalid_fields: set[str] = set()
        normalized_source_type = source_type.strip().lower()

        if not normalized_source_type:
            return "El tipo de fuente es obligatorio.", {"source_type"}

        if normalized_source_type == "folder" and not local_path.strip():
            return (
                "La ruta local es obligatoria cuando el tipo es folder.",
                {"local_path"},
            )

        if ingestion_channel == "upload_file" and normalized_source_type != "folder":
            return (
                "El canal de upload por archivo requiere tipo de fuente 'folder'.",
                set(),
            )

        if normalized_source_type == "confluence":
            has_base_url = bool(base_url.strip())
            has_token = bool(token.strip())
            if not has_base_url:
                invalid_fields.add("base_url")
            if not has_token:
                invalid_fields.add("token")
            if invalid_fields:
                return (
                    "URL base y token son obligatorios para fuentes confluence.",
                    invalid_fields,
                )

        if filters_raw.strip():
            parsed = self.safe_json(filters_raw.strip())
            is_invalid_json = parsed == {} and filters_raw.strip() not in {"{}", ""}
            if is_invalid_json:
                return "Los filtros deben ser un objeto JSON valido.", {"filters"}

        return None, set()

    @staticmethod
    def is_async_ready(payload: dict) -> bool:
        """Return True when async ingestion dependencies are reported ready."""
        ready = payload.get("ready")
        if isinstance(ready, bool):
            return ready
        return False