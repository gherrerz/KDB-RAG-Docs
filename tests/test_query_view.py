"""UI tests for query mode payload wiring in QueryView."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QMessageBox

from coderag.ui.query_view import DocumentPickerDialog, QueryView


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

    def _on_list_documents(
        source_id: str | None,
        tags: list[str] | None,
    ) -> dict[str, Any]:
        assert source_id == "src-1"
        assert tags == []
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


def test_query_view_refreshes_catalog_with_tag_filter() -> None:
    """Send catalog tags to list_documents without changing query payload."""
    _ensure_app()
    captured: dict[str, Any] = {}

    def _on_list_documents(
        source_id: str | None,
        tags: list[str] | None,
    ) -> dict[str, Any]:
        captured["source_id"] = source_id
        captured["tags"] = tags
        return {
            "count": 1,
            "documents": [
                {
                    "document_id": "doc-1",
                    "title": "engineering",
                    "path_or_url": "sample_data/engineering.md",
                    "source_id": "src-1",
                    "tags": ["finance", "urgent"],
                }
            ],
        }

    view = QueryView(
        lambda payload: {"answer": "ok", "diagnostics": {}, "citations": [], "graph_paths": []},
        on_list_documents=_on_list_documents,
    )
    view.source_id.setText("src-1")
    view.catalog_tags.setText("finance, urgent")

    refreshed = view._refresh_document_catalog(show_feedback=False)

    assert refreshed is True
    assert captured["source_id"] == "src-1"
    assert captured["tags"] == ["finance", "urgent"]
    assert view._available_documents[0]["tags"] == ["finance", "urgent"]


def test_query_view_loads_visible_tag_facets() -> None:
    """Render aggregated tag facets and allow applying one to the catalog filter."""
    _ensure_app()

    def _on_list_document_tags(source_id: str | None) -> dict[str, Any]:
        assert source_id == "src-1"
        return {
            "count": 2,
            "tags": ["finance", "urgent"],
            "items": [
                {"tag": "finance", "document_count": 3},
                {"tag": "urgent", "document_count": 1},
            ],
        }

    view = QueryView(
        lambda payload: {"answer": "ok", "diagnostics": {}, "citations": [], "graph_paths": []},
        on_list_document_tags=_on_list_document_tags,
    )
    view.source_id.setText("src-1")

    refreshed = view._refresh_tag_facets(show_feedback=False)

    assert refreshed is True
    assert view.tag_facets_list.count() == 2
    assert view.tag_facets_list.item(0).text() == "finance (3)"

    view._apply_tag_facet(view.tag_facets_list.item(0))
    assert view.catalog_tags.text() == "finance"


def test_document_picker_filter_matches_tags() -> None:
    """Allow free-text picker filter to match document tags."""
    _ensure_app()
    dialog = DocumentPickerDialog(
        documents=[
            {
                "document_id": "doc-1",
                "title": "engineering",
                "path_or_url": "sample_data/engineering.md",
                "source_id": "src-1",
                "tags": ["finance", "urgent"],
            },
            {
                "document_id": "doc-2",
                "title": "policy_finance",
                "path_or_url": "sample_data/policy_finance.md",
                "source_id": "src-1",
                "tags": ["policy"],
            },
        ],
        selected_ids=[],
    )

    dialog._apply_filter("urgent")

    assert dialog.list_widget.item(0).isHidden() is False
    assert dialog.list_widget.item(1).isHidden() is True


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


def test_query_view_replaces_tags_for_one_selected_document() -> None:
    """Update one selected document tags through the post-ingest edit action."""
    _ensure_app()
    replaced: list[tuple[str, list[str]]] = []

    def _on_replace_document_tags(
        document_id: str,
        tags: list[str],
    ) -> dict[str, Any]:
        replaced.append((document_id, tags))
        return {
            "status": "updated",
            "document_id": document_id,
            "new_tags": tags,
        }

    view = QueryView(
        lambda payload: {"answer": "ok", "diagnostics": {}, "citations": [], "graph_paths": []},
        on_replace_document_tags=_on_replace_document_tags,
    )
    view._available_documents = [
        {
            "document_id": "doc-1",
            "title": "engineering",
            "path_or_url": "sample_data/engineering.md",
            "source_id": "src-1",
            "tags": ["finance"],
        }
    ]
    view._set_selected_documents(view._available_documents)

    with patch(
        "coderag.ui.query_view.QInputDialog.getText",
        return_value=("legal, approved", True),
    ):
        view._edit_selected_document_tags()

    assert replaced == [("doc-1", ["legal", "approved"])]
    assert view._selected_documents[0]["tags"] == ["legal", "approved"]
    assert view._available_documents[0]["tags"] == ["legal", "approved"]
    assert "actualizadas" in view.status_message.text().casefold()


def test_query_view_replaces_tags_for_multiple_selected_documents() -> None:
    """Apply one replacement tag set to all selected documents."""
    _ensure_app()
    replaced: list[tuple[str, list[str]]] = []

    def _on_replace_document_tags(
        document_id: str,
        tags: list[str],
    ) -> dict[str, Any]:
        replaced.append((document_id, tags))
        return {
            "status": "updated",
            "document_id": document_id,
            "new_tags": tags,
        }

    view = QueryView(
        lambda payload: {"answer": "ok", "diagnostics": {}, "citations": [], "graph_paths": []},
        on_replace_document_tags=_on_replace_document_tags,
    )
    view._available_documents = [
        {
            "document_id": "doc-1",
            "title": "engineering",
            "path_or_url": "sample_data/engineering.md",
            "source_id": "src-1",
            "tags": ["finance"],
        },
        {
            "document_id": "doc-2",
            "title": "policy_finance",
            "path_or_url": "sample_data/policy_finance.md",
            "source_id": "src-1",
            "tags": ["policy"],
        },
    ]
    view._set_selected_documents(view._available_documents)

    with patch(
        "coderag.ui.query_view.QInputDialog.getText",
        return_value=("shared, reviewed", True),
    ):
        view._edit_selected_document_tags()

    assert replaced == [
        ("doc-1", ["shared", "reviewed"]),
        ("doc-2", ["shared", "reviewed"]),
    ]
    assert all(
        item["tags"] == ["shared", "reviewed"]
        for item in view._available_documents
    )


def test_query_view_enables_tag_edit_only_for_single_selection() -> None:
    """Enable tag editing whenever at least one selected document exists."""
    _ensure_app()

    view = QueryView(
        lambda payload: {"answer": "ok", "diagnostics": {}, "citations": [], "graph_paths": []},
        on_replace_document_tags=lambda document_id, tags: {"status": "updated"},
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

    view._refresh_document_catalog_state()
    assert view.edit_tags_button.isEnabled() is False

    view._set_selected_documents([view._available_documents[0]])
    assert view.edit_tags_button.isEnabled() is True

    view._set_selected_documents(view._available_documents)
    assert view.edit_tags_button.isEnabled() is True


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
