"""UI tests for query mode payload wiring in QueryView."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QMessageBox

from coderag.ui.query_view import QueryView


def _ensure_app() -> QApplication:
    """Return a QApplication instance for widget tests."""
    app = QApplication.instance()
    if app is not None:
        return app
    return QApplication([])


def test_query_view_sends_include_llm_answer_true_by_default() -> None:
    """Send include_llm_answer=true when checkbox remains checked."""
    _ensure_app()
    captured_payload: dict[str, Any] = {}

    def _on_query(payload: dict[str, Any]) -> dict[str, Any]:
        captured_payload.update(payload)
        return {
            "answer": "ok",
            "diagnostics": {},
            "citations": [],
            "graph_paths": [],
        }

    view = QueryView(_on_query)
    view.question.setText("What is ISO 27001?")
    view.source_id.setText("")
    view.hops.setText("2")

    view._run_query()

    assert captured_payload["include_llm_answer"] is True
    assert captured_payload["hops"] == 2


def test_query_view_sends_include_llm_answer_false_when_unchecked() -> None:
    """Send include_llm_answer=false when checkbox is disabled by user."""
    _ensure_app()
    captured_payload: dict[str, Any] = {}

    def _on_query(payload: dict[str, Any]) -> dict[str, Any]:
        captured_payload.update(payload)
        return {
            "answer": "ok",
            "diagnostics": {},
            "citations": [],
            "graph_paths": [],
        }

    view = QueryView(_on_query)
    view.question.setText("What is ISO 27001?")
    view.hops.setText("2")
    view.include_llm_answer.setChecked(False)

    view._run_query()

    assert captured_payload["include_llm_answer"] is False
    assert captured_payload["hops"] == 2


def test_query_view_requires_non_empty_question() -> None:
    """Avoid backend call when question is empty."""
    _ensure_app()
    calls = 0

    def _on_query(payload: dict[str, Any]) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {
            "answer": "ok",
            "diagnostics": {},
            "citations": [],
            "graph_paths": [],
        }

    view = QueryView(_on_query)
    view.question.setText("   ")
    view.hops.setText("2")

    view._run_query()

    assert calls == 0
    assert "Error de validacion" in view.answer.toPlainText()


def test_query_view_requires_hops_between_1_and_6() -> None:
    """Reject graph hops out of supported range before sending payload."""
    _ensure_app()
    calls = 0

    def _on_query(payload: dict[str, Any]) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {
            "answer": "ok",
            "diagnostics": {},
            "citations": [],
            "graph_paths": [],
        }

    view = QueryView(_on_query)
    view.question.setText("What is ISO 27001?")
    view.hops.setText("9")

    view._run_query()

    assert calls == 0
    assert "Error de validacion" in view.answer.toPlainText()


def test_query_view_sends_selected_document_ids() -> None:
    """Include selected document ids in payload when user narrows Query scope."""
    _ensure_app()
    captured_payload: dict[str, Any] = {}

    def _on_query(payload: dict[str, Any]) -> dict[str, Any]:
        captured_payload.update(payload)
        return {
            "answer": "ok",
            "diagnostics": {},
            "citations": [],
            "graph_paths": [],
        }

    view = QueryView(_on_query)
    view.question.setText("Who works on Project Atlas?")
    view.hops.setText("2")
    view._set_selected_documents(
        [
            {
                "document_id": "doc-1",
                "title": "engineering",
                "path_or_url": "sample_data/engineering.md",
                "source_id": "src-1",
            },
            {
                "document_id": "doc-2",
                "title": "policy_finance",
                "path_or_url": "sample_data/policy_finance.md",
                "source_id": "src-1",
            },
        ]
    )

    view._run_query()

    assert captured_payload["document_ids"] == ["doc-1", "doc-2"]
    assert "engineering" in view.selected_documents_label.text()


def test_query_view_prunes_selected_documents_when_source_id_changes() -> None:
    """Drop document selections that no longer match the chosen source_id."""
    _ensure_app()

    view = QueryView(lambda payload: {"answer": "ok", "diagnostics": {}, "citations": [], "graph_paths": []})
    view._set_selected_documents(
        [
            {
                "document_id": "doc-1",
                "title": "engineering",
                "path_or_url": "sample_data/engineering.md",
                "source_id": "src-1",
            },
            {
                "document_id": "doc-2",
                "title": "policy_finance",
                "path_or_url": "sample_data/policy_finance.md",
                "source_id": "src-2",
            },
        ]
    )

    view.source_id.setText("src-1")

    assert view.selected_document_ids() == ["doc-1"]
    assert "engineering" in view.selected_documents_label.text()


def test_query_view_refreshes_catalog_and_updates_picker_state() -> None:
    """Reflect available document count in picker state after catalog refresh."""
    _ensure_app()

    def _on_list_documents(source_id: str | None) -> dict[str, Any]:
        assert source_id == "src-1"
        return {
            "count": 2,
            "documents": [
                {
                    "document_id": "doc-1",
                    "title": "engineering",
                    "path_or_url": "sample_data/engineering.md",
                    "source_id": "src-1",
                },
                {
                    "document_id": "doc-2",
                    "title": "policy_finance",
                    "path_or_url": "sample_data/policy_finance.md",
                    "source_id": "src-1",
                },
            ],
        }

    view = QueryView(
        lambda payload: {"answer": "ok", "diagnostics": {}, "citations": [], "graph_paths": []},
        on_list_documents=_on_list_documents,
    )
    view.source_id.setText("src-1")

    refreshed = view._refresh_document_catalog(show_feedback=False)

    assert refreshed is True
    assert view.document_picker_button.isEnabled() is True
    assert "2 docs" in view.document_catalog_label.text()


def test_query_view_disables_picker_when_catalog_unavailable() -> None:
    """Render unavailable state when no catalog callback exists."""
    _ensure_app()

    view = QueryView(
        lambda payload: {"answer": "ok", "diagnostics": {}, "citations": [], "graph_paths": []}
    )

    refreshed = view._refresh_document_catalog(show_feedback=False)

    assert refreshed is False
    assert view.document_picker_button.isEnabled() is False
    assert "no disponible" in view.document_catalog_label.text().casefold()


def test_query_view_deletes_selected_documents_and_updates_state() -> None:
    """Remove selected documents from UI state after confirmed delete."""
    _ensure_app()
    deleted_ids: list[str] = []

    def _on_delete_document(document_id: str) -> dict[str, Any]:
        deleted_ids.append(document_id)
        return {
            "status": "completed",
            "document_id": document_id,
        }

    view = QueryView(
        lambda payload: {"answer": "ok", "diagnostics": {}, "citations": [], "graph_paths": []},
        on_delete_document=_on_delete_document,
    )
    view._available_documents = [
        {
            "document_id": "doc-1",
            "title": "engineering",
            "path_or_url": "sample_data/engineering.md",
            "source_id": "src-1",
        },
        {
            "document_id": "doc-2",
            "title": "policy_finance",
            "path_or_url": "sample_data/policy_finance.md",
            "source_id": "src-1",
        },
    ]
    view._set_selected_documents(view._available_documents)

    with patch(
        "coderag.ui.query_view.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    ):
        view._delete_selected_documents()

    assert deleted_ids == ["doc-1", "doc-2"]
    assert view.selected_document_ids() == []
    assert view._available_documents == []
    assert "documentos eliminados" in view.status_message.text().casefold()


def test_query_view_disables_delete_when_no_selection_exists() -> None:
    """Keep delete action disabled until at least one document is selected."""
    _ensure_app()

    view = QueryView(
        lambda payload: {"answer": "ok", "diagnostics": {}, "citations": [], "graph_paths": []},
        on_delete_document=lambda document_id: {"status": "completed"},
    )
    view._available_documents = [
        {
            "document_id": "doc-1",
            "title": "engineering",
            "path_or_url": "sample_data/engineering.md",
            "source_id": "src-1",
        }
    ]

    view._refresh_document_catalog_state()
    assert view.delete_documents_button.isEnabled() is False

    view._set_selected_documents(view._available_documents)
    assert view.delete_documents_button.isEnabled() is True
