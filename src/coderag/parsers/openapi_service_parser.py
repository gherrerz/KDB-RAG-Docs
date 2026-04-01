"""Parse OpenAPI documents into service-to-endpoint mapping assets."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

HTTP_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options",
}

PATH_BLOCK_PATTERN = re.compile(r"^\s*/[^:]+:\s*$")
METHOD_PATTERN = re.compile(
    r"^\s{2,}(get|post|put|patch|delete|head|options):\s*$",
    re.IGNORECASE,
)
TABLE_HINT_PATTERN = re.compile(
    r"x-table(?:-name)?\s*:\s*[\"']?(?P<name>[\w\.\-]+)",
    re.IGNORECASE,
)


def _derive_service_name(path_hint: str, payload: Dict[str, Any]) -> str:
    """Resolve service name from OpenAPI info section or path hint."""
    info = payload.get("info") if isinstance(payload, dict) else None
    if isinstance(info, dict):
        title = str(info.get("title") or "").strip()
        if title:
            return title

    fallback = path_hint.rsplit("/", 1)[-1].strip()
    if "." in fallback:
        fallback = fallback.rsplit(".", 1)[0]
    return fallback or "unknown-service"


def _parse_openapi_json(
    text: str,
    path_hint: str,
) -> Dict[str, Any] | None:
    """Parse OpenAPI JSON payload using native json module."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    paths = payload.get("paths", {})
    if not isinstance(paths, dict):
        return None

    service_name = _derive_service_name(path_hint, payload)
    mappings: List[Dict[str, Any]] = []
    for endpoint, methods in paths.items():
        if not isinstance(endpoint, str) or not isinstance(methods, dict):
            continue
        for method, operation in methods.items():
            lowered = str(method).lower()
            if lowered not in HTTP_METHODS:
                continue
            operation_id = ""
            table_name = None
            if isinstance(operation, dict):
                operation_id = str(operation.get("operationId") or "")
                table_name = operation.get("x-table") or operation.get(
                    "x-table-name"
                )

            mappings.append(
                {
                    "service_name": service_name,
                    "endpoint": endpoint,
                    "method": lowered.upper(),
                    "operation_id": operation_id,
                    "table_name": str(table_name).strip() if table_name else None,
                }
            )

    return {"service_name": service_name, "mappings": mappings}


def _parse_openapi_yaml_like(
    text: str,
    path_hint: str,
) -> Dict[str, Any]:
    """Best-effort parser for YAML-like OpenAPI files without dependencies."""
    service_name = ""
    current_path = ""
    current_method = ""
    current_table: str | None = None
    mappings: List[Dict[str, Any]] = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.lower().startswith("title:") and not service_name:
            service_name = stripped.split(":", 1)[1].strip().strip('"\'')
            continue

        if PATH_BLOCK_PATTERN.match(line):
            current_path = stripped.rstrip(":")
            current_method = ""
            current_table = None
            continue

        method_match = METHOD_PATTERN.match(line)
        if method_match and current_path:
            current_method = method_match.group(1).upper()
            current_table = None
            mappings.append(
                {
                    "service_name": service_name or "",
                    "endpoint": current_path,
                    "method": current_method,
                    "operation_id": "",
                    "table_name": None,
                }
            )
            continue

        if current_path and current_method:
            table_hint_match = TABLE_HINT_PATTERN.search(stripped)
            if table_hint_match and mappings:
                current_table = table_hint_match.group("name").strip()
                mappings[-1]["table_name"] = current_table

    resolved_service = service_name or _derive_service_name(path_hint, {})
    for item in mappings:
        item["service_name"] = resolved_service
    return {"service_name": resolved_service, "mappings": mappings}


def parse_openapi_service_contract(
    text: str,
    path_hint: str,
) -> Dict[str, Any]:
    """Extract endpoint-to-service mappings from OpenAPI JSON/YAML text."""
    parsed_json = _parse_openapi_json(text=text, path_hint=path_hint)
    if parsed_json is not None:
        return parsed_json
    return _parse_openapi_yaml_like(text=text, path_hint=path_hint)
