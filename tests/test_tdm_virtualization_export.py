"""Tests for TDM virtualization template exporter."""

from __future__ import annotations

from coderag.tdm.virtualization_export import build_virtualization_templates


def test_build_virtualization_templates_filters_by_service() -> None:
    """Create templates and apply service-level filtering."""
    templates = build_virtualization_templates(
        source_id="src-1",
        mappings=[
            {
                "service_name": "billing-api",
                "endpoint": "/v1/invoices",
                "method": "GET",
                "table_id": "table-1",
            },
            {
                "service_name": "inventory-api",
                "endpoint": "/v1/items",
                "method": "GET",
                "table_id": "table-2",
            },
        ],
        service_name_filter="billing-api",
    )

    assert len(templates) == 1
    template = templates[0]
    assert template["service_name"] == "billing-api"
    assert template["content"]["request"]["path"] == "/v1/invoices"
    assert "artifact_id" in template
