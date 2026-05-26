"""Document catalog controller helpers for QueryView state handling."""

from __future__ import annotations

from typing import Any, Sequence


class DocumentCatalogController:
    """Encapsula transformaciones del catálogo y selección de documentos."""

    @staticmethod
    def parse_tags_payload(raw_tags: object) -> list[str]:
        """Normalize tag values coming from UI text or API payloads."""
        if isinstance(raw_tags, list):
            values = raw_tags
        else:
            values = str(raw_tags or "").split(",")

        normalized: list[str] = []
        seen: set[str] = set()
        for raw_tag in values:
            tag = str(raw_tag or "").strip()
            if not tag:
                continue
            tag_key = tag.casefold()
            if tag_key in seen:
                continue
            seen.add(tag_key)
            normalized.append(tag)
        return normalized

    def normalize_selected_documents(
        self,
        documents: Sequence[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Store a normalized list of selected document metadata rows."""
        normalized: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for item in documents:
            if not isinstance(item, dict):
                continue
            document_id = str(item.get("document_id") or "").strip()
            if not document_id or document_id in seen_ids:
                continue
            seen_ids.add(document_id)
            normalized.append(
                {
                    "document_id": document_id,
                    "title": str(item.get("title") or document_id),
                    "path_or_url": str(item.get("path_or_url") or ""),
                    "source_id": str(item.get("source_id") or ""),
                    "tags": self.parse_tags_payload(item.get("tags")),
                }
            )
        return normalized

    @staticmethod
    def selected_document_ids(documents: Sequence[dict[str, Any]]) -> list[str]:
        """Return selected document ids in UI order for payload wiring."""
        return [
            str(item.get("document_id") or "")
            for item in documents
            if str(item.get("document_id") or "")
        ]

    @staticmethod
    def summarize_selected_documents(documents: Sequence[dict[str, Any]]) -> str:
        """Render a compact human-readable summary of filter state."""
        if not documents:
            return "Sin filtro por documento"

        labels = [
            str(item.get("title") or item.get("document_id") or "")
            for item in documents
        ]
        if len(labels) == 1:
            return labels[0]
        if len(labels) == 2:
            return f"{labels[0]} y {labels[1]}"
        return f"{labels[0]}, {labels[1]} y {len(labels) - 2} mas"

    @staticmethod
    def prune_selected_documents(
        selected_documents: Sequence[dict[str, Any]],
        available_documents: Sequence[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Remove selected documents that are no longer present in catalog."""
        allowed_ids = {
            str(item.get("document_id") or "")
            for item in available_documents
            if str(item.get("document_id") or "")
        }
        if not allowed_ids:
            return []
        return [
            item
            for item in selected_documents
            if str(item.get("document_id") or "") in allowed_ids
        ]