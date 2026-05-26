"""Presenter helpers for TDM UI payload and result transformations."""

from __future__ import annotations

import json
from typing import Any


class TdmPresenter:
    """Encapsula payload builders y normalizacion de resultados TDM."""

    @staticmethod
    def optional(raw: str) -> str | None:
        """Convert empty strings to None for optional payload fields."""
        value = raw.strip()
        return value or None

    @staticmethod
    def safe_json(raw: str) -> dict[str, Any]:
        """Parse JSON object safely, defaulting to empty dict."""
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
        return {}

    @staticmethod
    def safe_int(raw: str) -> int | None:
        """Parse integer safely and return None when invalid."""
        try:
            return int(raw)
        except ValueError:
            return None

    def build_ingest_payload(
        self,
        *,
        source_type: str,
        local_path: str,
        filters_raw: str,
    ) -> dict[str, Any]:
        """Build payload for /tdm/ingest endpoint."""
        return {
            "source": {
                "source_type": source_type.strip() or "tdm_folder",
                "local_path": local_path.strip(),
                "filters": self.safe_json(filters_raw.strip()),
            }
        }

    def build_query_payload(
        self,
        *,
        question: str,
        source_id: str,
        service_name: str,
        table_name: str,
        include_virtualization_preview: bool,
    ) -> dict[str, Any]:
        """Build payload for /tdm/query endpoint."""
        return {
            "question": question.strip(),
            "source_id": self.optional(source_id),
            "service_name": self.optional(service_name),
            "table_name": self.optional(table_name),
            "include_virtualization_preview": include_virtualization_preview,
        }

    def build_virtualization_preview_payload(
        self,
        *,
        question: str,
        source_id: str,
        service_name: str,
        table_name: str,
    ) -> dict[str, Any]:
        """Build payload for /tdm/virtualization/preview endpoint."""
        return {
            "question": question.strip() or "virtualization preview",
            "source_id": self.optional(source_id),
            "service_name": self.optional(service_name),
            "table_name": self.optional(table_name),
            "include_virtualization_preview": True,
        }

    @staticmethod
    def hint_for_error_detail(detail: str) -> str:
        """Map backend error details into actionable UI hints."""
        lowered = detail.casefold()
        if "tdm endpoints are disabled" in lowered:
            return "TDM deshabilitado (ENABLE_TDM=false)."
        if "tdm virtualization is disabled" in lowered:
            return "Virtualization deshabilitada (TDM_ENABLE_VIRTUALIZATION=false)."
        if "tdm synthetic planning is disabled" in lowered:
            return "Synthetic deshabilitado (TDM_ENABLE_SYNTHETIC=false)."
        if "disabled" in lowered:
            return "Capacidad TDM deshabilitada por feature flag."
        if "503" in lowered or "service unavailable" in lowered:
            return "Backend TDM no disponible temporalmente (503)."
        return "Operacion TDM fallo."

    @staticmethod
    def extract_result_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
        """Normalize response payloads into rows for tabular rendering."""
        rows: list[dict[str, Any]] = []

        findings = result.get("findings")
        if isinstance(findings, list):
            for finding in findings:
                if not isinstance(finding, dict):
                    continue
                rows.append(
                    {
                        "type": "finding",
                        "primary": str(
                            finding.get("service_name")
                            or finding.get("table_name")
                            or finding.get("column_name")
                            or finding.get("mapping_id")
                            or "item"
                        ),
                        "secondary": str(
                            finding.get("endpoint")
                            or finding.get("table_id")
                            or finding.get("data_type")
                            or ""
                        ),
                        "notes": str(
                            finding.get("method")
                            or finding.get("pii_class")
                            or ""
                        ),
                        "raw": finding,
                    }
                )

        mappings = result.get("mappings")
        if isinstance(mappings, list):
            for mapping in mappings:
                if not isinstance(mapping, dict):
                    continue
                rows.append(
                    {
                        "type": "service_mapping",
                        "primary": str(mapping.get("service_name") or ""),
                        "secondary": str(mapping.get("endpoint") or ""),
                        "notes": str(mapping.get("method") or ""),
                        "raw": mapping,
                    }
                )

        tables = result.get("tables")
        if isinstance(tables, list):
            for table in tables:
                if not isinstance(table, dict):
                    continue
                rows.append(
                    {
                        "type": "table",
                        "primary": str(table.get("table_name") or ""),
                        "secondary": str(table.get("table_id") or ""),
                        "notes": str(table.get("schema_id") or ""),
                        "raw": table,
                    }
                )

        columns = result.get("columns")
        if isinstance(columns, list):
            for column in columns:
                if not isinstance(column, dict):
                    continue
                rows.append(
                    {
                        "type": "column",
                        "primary": str(column.get("column_name") or ""),
                        "secondary": str(column.get("data_type") or ""),
                        "notes": str(column.get("pii_class") or ""),
                        "raw": column,
                    }
                )

        templates = result.get("templates")
        if isinstance(templates, list):
            for template in templates:
                if not isinstance(template, dict):
                    continue
                request = template.get("content", {}).get("request", {})
                if not isinstance(request, dict):
                    request = {}
                rows.append(
                    {
                        "type": "virtualization",
                        "primary": str(template.get("service_name") or ""),
                        "secondary": str(request.get("path") or ""),
                        "notes": str(request.get("method") or ""),
                        "raw": template,
                    }
                )

        plan = result.get("plan")
        if isinstance(plan, dict):
            rows.append(
                {
                    "type": "synthetic_plan",
                    "primary": str(plan.get("table_name") or result.get("table_name") or ""),
                    "secondary": str(plan.get("target_rows") or ""),
                    "notes": str(plan.get("strategy") or ""),
                    "raw": plan,
                }
            )

        return rows