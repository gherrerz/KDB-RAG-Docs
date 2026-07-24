"""Pruebas de los prompts MCP (guías de uso de consulta, ingesta y catálogo)."""

import asyncio

import mcp.types as t
from mcp.server.lowlevel import Server

from coderag.api.mcp_prompts import register_mcp_prompts


def _server_with_prompts() -> Server:
    server = Server("test")
    register_mcp_prompts(server)
    return server


def test_register_returns_expected_count() -> None:
    server = Server("test")
    assert register_mcp_prompts(server) == 3


def test_list_prompts_exposes_the_three_guides() -> None:
    server = _server_with_prompts()
    handler = server.request_handlers[t.ListPromptsRequest]
    req = t.ListPromptsRequest(method="prompts/list")
    result = asyncio.run(handler(req)).root
    names = {p.name for p in result.prompts}
    assert names == {
        "query_guide",
        "ingest_workflow_guide",
        "document_catalog_guide",
    }


def test_query_guide_declares_required_arguments() -> None:
    server = _server_with_prompts()
    handler = server.request_handlers[t.ListPromptsRequest]
    result = asyncio.run(handler(t.ListPromptsRequest(method="prompts/list"))).root
    guide = next(p for p in result.prompts if p.name == "query_guide")
    required = {a.name for a in guide.arguments if a.required}
    assert required == {"pregunta"}


def test_get_prompt_substitutes_placeholders() -> None:
    server = _server_with_prompts()
    handler = server.request_handlers[t.GetPromptRequest]
    req = t.GetPromptRequest(
        method="prompts/get",
        params=t.GetPromptRequestParams(
            name="query_guide",
            arguments={"pregunta": "dónde está X"},
        ),
    )
    result = asyncio.run(handler(req)).root
    text = result.messages[0].content.text
    assert "dónde está X" in text
    assert result.messages[0].role == "user"


def test_ingest_workflow_guide_keeps_uri_template_literal() -> None:
    """El flujo sin args conserva {document_id} literal en el patrón del URI."""
    server = _server_with_prompts()
    handler = server.request_handlers[t.GetPromptRequest]
    req = t.GetPromptRequest(
        method="prompts/get",
        params=t.GetPromptRequestParams(
            name="ingest_workflow_guide", arguments=None
        ),
    )
    result = asyncio.run(handler(req)).root
    assert "rag://documents/{document_id}" in result.messages[0].content.text


def test_document_catalog_guide_mentions_idempotent_tags() -> None:
    server = _server_with_prompts()
    handler = server.request_handlers[t.GetPromptRequest]
    req = t.GetPromptRequest(
        method="prompts/get",
        params=t.GetPromptRequestParams(
            name="document_catalog_guide", arguments=None
        ),
    )
    result = asyncio.run(handler(req)).root
    assert "replace_document_tags" in result.messages[0].content.text
