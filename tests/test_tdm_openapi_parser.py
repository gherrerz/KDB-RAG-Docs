"""Unit tests for OpenAPI parser used by TDM ingestion."""

from __future__ import annotations

from coderag.parsers.openapi_service_parser import parse_openapi_service_contract


def test_parse_openapi_json_extracts_service_mappings() -> None:
    """Extract endpoint and method mappings from OpenAPI JSON text."""
    payload = """
    {
      "openapi": "3.0.0",
      "info": {"title": "billing-api"},
      "paths": {
        "/v1/invoices": {
          "get": {"operationId": "listInvoices", "x-table": "billing.invoices"}
        },
        "/v1/customers": {
          "post": {"operationId": "createCustomer"}
        }
      }
    }
    """

    parsed = parse_openapi_service_contract(payload, path_hint="openapi.json")

    assert parsed["service_name"] == "billing-api"
    assert len(parsed["mappings"]) == 2
    assert any(
        item["endpoint"] == "/v1/invoices"
        and item["method"] == "GET"
        and item["table_name"] == "billing.invoices"
        for item in parsed["mappings"]
    )
    assert any(
        item["endpoint"] == "/v1/customers"
        and item["method"] == "POST"
        for item in parsed["mappings"]
    )


def test_parse_openapi_yaml_like_extracts_minimal_mappings() -> None:
    """Support dependency-free YAML-like OpenAPI mapping extraction."""
    payload = """
    openapi: 3.0.0
    info:
      title: inventory-api
    paths:
      /v1/items:
        get:
          x-table: inventory.items
    """

    parsed = parse_openapi_service_contract(payload, path_hint="inventory.yaml")

    assert parsed["service_name"] == "inventory-api"
    assert len(parsed["mappings"]) == 1
    mapping = parsed["mappings"][0]
    assert mapping["endpoint"] == "/v1/items"
    assert mapping["method"] == "GET"
    assert mapping["table_name"] == "inventory.items"
