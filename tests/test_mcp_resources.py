"""Pruebas de los resources MCP (guías estáticas + catálogo documental en vivo)."""

import asyncio

import httpx
import mcp.types as t
import pytest
from mcp.server.lowlevel import Server
from pydantic import AnyUrl

from coderag.api.mcp_resources import register_mcp_resources


def _mock_client() -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sources/documents":
            return httpx.Response(
                200, json={"count": 1, "documents": [{"document_id": "doc-1"}]}
            )
        if request.url.path == "/sources/documents/doc-1/content":
            return httpx.Response(
                200, json={"document_id": "doc-1", "content": "hola"}
            )
        if request.url.path == "/sources/ingest/readiness":
            return httpx.Response(200, json={"ready": True, "recommendation": "async"})
        return httpx.Response(404, json={"detail": "not found"})

    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://apiserver"
    )


def _server() -> Server:
    server = Server("test")
    register_mcp_resources(server, _mock_client())
    return server


def _read(server: Server, uri: str) -> str:
    handler = server.request_handlers[t.ReadResourceRequest]
    req = t.ReadResourceRequest(
        method="resources/read",
        params=t.ReadResourceRequestParams(uri=AnyUrl(uri)),
    )
    return asyncio.run(handler(req)).root.contents[0].text


def test_register_counts_fixed_resources() -> None:
    server = Server("test")
    # 5 guías estáticas + rag://documents + rag://ingest/readiness
    assert register_mcp_resources(server, _mock_client()) == 7


def test_list_resources_includes_guides_and_documents() -> None:
    server = _server()
    handler = server.request_handlers[t.ListResourcesRequest]
    result = asyncio.run(handler(t.ListResourcesRequest(method="resources/list"))).root
    uris = {str(r.uri) for r in result.resources}
    assert "rag://documents" in uris
    assert "rag://ingest/readiness" in uris
    assert "rag://guide/query-cookbook" in uris
    assert "rag://guide/capabilities" in uris


def test_list_resource_templates_includes_document_content() -> None:
    server = _server()
    handler = server.request_handlers[t.ListResourceTemplatesRequest]
    req = t.ListResourceTemplatesRequest(method="resources/templates/list")
    result = asyncio.run(handler(req)).root
    templates = {tpl.uriTemplate for tpl in result.resourceTemplates}
    assert "rag://documents/{document_id}" in templates


def test_read_static_resource_returns_markdown() -> None:
    text = _read(_server(), "rag://guide/tools-overview")
    assert "Tools MCP disponibles" in text


def test_read_documents_returns_live_catalog() -> None:
    text = _read(_server(), "rag://documents")
    assert "doc-1" in text


def test_read_document_content_returns_text() -> None:
    text = _read(_server(), "rag://documents/doc-1")
    assert "hola" in text


def test_read_ingest_readiness_returns_status() -> None:
    text = _read(_server(), "rag://ingest/readiness")
    assert "ready" in text


def test_read_document_content_handles_upstream_error() -> None:
    """Un document_id inexistente no propaga excepción: devuelve JSON de error."""
    text = _read(_server(), "rag://documents/ghost")
    assert "error" in text
    assert "status_code" in text


def test_read_unknown_resource_raises() -> None:
    with pytest.raises(ValueError):
        _read(_server(), "rag://nope")
