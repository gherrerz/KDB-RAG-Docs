"""Virtualization artifact builders for TDM service mappings."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable, List


def _artifact_id(
    source_id: str,
    service_name: str,
    endpoint: str,
    method: str,
) -> str:
    """Build deterministic artifact identifiers for persistence."""
    raw = f"{source_id}:{service_name}:{method}:{endpoint}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def build_virtualization_templates(
    source_id: str,
    mappings: Iterable[Dict[str, Any]],
    service_name_filter: str | None = None,
) -> List[Dict[str, Any]]:
    """Create neutral virtualization templates from service mappings."""
    templates: List[Dict[str, Any]] = []
    for item in mappings:
        service_name = str(item.get("service_name") or "").strip()
        endpoint = str(item.get("endpoint") or "").strip()
        method = str(item.get("method") or "GET").upper()
        if not service_name or not endpoint:
            continue
        if service_name_filter and service_name.casefold() != service_name_filter.casefold():
            continue

        templates.append(
            {
                "artifact_id": _artifact_id(
                    source_id=source_id,
                    service_name=service_name,
                    endpoint=endpoint,
                    method=method,
                ),
                "service_name": service_name,
                "artifact_type": "mock-template",
                "content": {
                    "request": {
                        "method": method,
                        "path": endpoint,
                    },
                    "response": {
                        "status": 200,
                        "headers": {"content-type": "application/json"},
                        "body": {
                            "source": "tdm-virtualization",
                            "endpoint": endpoint,
                        },
                    },
                },
                "metadata": {
                    "table_id": item.get("table_id"),
                    "operation_id": item.get("metadata", {}).get("operation_id"),
                },
            }
        )
    return templates
