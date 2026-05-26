"""Unit tests for QueryPresenter and document catalog controller."""

from __future__ import annotations

from coderag.ui.document_catalog_controller import DocumentCatalogController
from coderag.ui.query_presenter import QueryPresenter


def test_query_presenter_validates_hops_range() -> None:
    """Reject hops outside supported range before backend call."""
    presenter = QueryPresenter()

    error, invalid = presenter.validate_inputs(question="What is ISO 27001?", hops_raw="9")

    assert "saltos" in str(error)
    assert invalid == {"hops"}


def test_query_presenter_build_payload_includes_optional_none() -> None:
    """Build payload with optional source_id normalized to None."""
    presenter = QueryPresenter()

    payload = presenter.build_payload(
        question="impacto",
        source_id="",
        document_ids=["doc-1"],
        hops_raw="2",
        include_llm_answer=True,
    )

    assert payload["source_id"] is None
    assert payload["hops"] == 2
    assert payload["document_ids"] == ["doc-1"]


def test_document_catalog_controller_normalizes_and_summarizes_selection() -> None:
    """Normalize selections and produce compact selection summary."""
    controller = DocumentCatalogController()

    selected = controller.normalize_selected_documents(
        [
            {"document_id": "doc-1", "title": "engineering", "tags": ["finance"]},
            {"document_id": "doc-2", "title": "policy", "tags": ["urgent"]},
            {"document_id": "doc-1", "title": "dup"},
        ]
    )

    assert controller.selected_document_ids(selected) == ["doc-1", "doc-2"]
    assert "engineering" in controller.summarize_selected_documents(selected)
