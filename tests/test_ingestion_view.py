"""UI tests for ingestion form validation and progress rendering."""

from __future__ import annotations

import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QMessageBox

from coderag.ui.ingestion_view import IngestionView


def _ensure_app() -> QApplication:
    """Return a QApplication instance for widget tests."""
    app = QApplication.instance()
    if app is not None:
        return app
    return QApplication([])


def _build_view() -> IngestionView:
    """Create an ingestion view with lightweight callback stubs."""
    _ensure_app()

    def _on_ingest(payload: dict, on_update=None) -> dict:
        return {
            "status": "completed",
            "progress_pct": 100,
            "message": "ok",
            "documents": 1,
            "chunks": 2,
            "steps": [],
        }

    def _on_reset_all() -> dict:
        return {
            "status": "completed",
            "message": "reset done",
            "documents": 0,
            "chunks": 0,
            "steps": [],
        }

    def _on_delete_document(document_id: str) -> dict:
        return {
            "status": "completed",
            "message": f"deleted {document_id}",
            "document_id": document_id,
            "source_id": "src-1",
            "deleted_documents": 1,
            "deleted_chunks": 3,
            "deleted_staging_files": 1,
            "reindexed_sources": 0,
        }

    return IngestionView(_on_ingest, _on_reset_all, _on_delete_document)


def test_ingestion_view_requires_local_path_for_folder_source() -> None:
    """Reject folder ingestion when local_path is empty."""
    view = _build_view()
    view.source_type.setText("folder")
    view.local_path.setText("   ")

    error = view._validate_inputs()

    assert error == "La ruta local es obligatoria cuando el tipo es folder."


def test_ingestion_view_requires_confluence_credentials() -> None:
    """Reject confluence source without base_url and token."""
    view = _build_view()
    view.source_type.setText("confluence")
    view.base_url.setText("")
    view.token.setText("")

    error = view._validate_inputs()

    assert error == "URL base y token son obligatorios para fuentes confluence."


def test_ingestion_view_requires_valid_filters_json() -> None:
    """Reject invalid filters payload to prevent backend errors."""
    view = _build_view()
    view.source_type.setText("folder")
    view.local_path.setText("sample_data")
    view.filters.setText("{not-json}")

    error = view._validate_inputs()

    assert error == "Los filtros deben ser un objeto JSON valido."


def test_ingestion_view_updates_progress_and_summary_from_live_update() -> None:
    """Render concise progress state from backend live updates."""
    view = _build_view()
    result = {
        "status": "running",
        "progress_pct": 67.3,
        "message": "indexing",
        "documents": 8,
        "chunks": 120,
        "deduplication": {
            "incoming_batch": {
                "skipped_documents": 1,
                "kept_paths": ["storage/ingestion_staging/new/atlas.md"],
            },
            "replaced_existing": {
                "deleted_documents": 2,
                "replaced_paths": ["storage/ingestion_staging/old/atlas.md"],
            },
        },
        "steps": [{"elapsed_hhmmss": "00:01:12"}],
    }

    view._handle_live_update(result)

    assert view.progress.value() == 67
    summary = view.summary.toPlainText()
    assert "Estado: en curso" in summary
    assert "Documentos: 8" in summary
    assert "Chunks: 120" in summary
    assert "Deduplicacion: lote=1 | reemplazos=2" in summary
    assert "Detalle deduplicacion:" in summary
    assert "storage/ingestion_staging/old/atlas.md" in summary


def test_ingestion_view_formats_deduplication_details() -> None:
    """Render deduplication sections in the technical ingestion output."""
    rendered = IngestionView._format_ingestion_result(
        {
            "status": "completed",
            "documents": 1,
            "chunks": 2,
            "deduplication": {
                "incoming_batch": {
                    "skipped_documents": 1,
                    "kept_paths": ["storage/ingestion_staging/new/atlas.md"],
                },
                "replaced_existing": {
                    "deleted_documents": 2,
                    "replaced_paths": ["storage/ingestion_staging/old/atlas.md"],
                },
            },
        },
        include_raw=False,
    )

    assert "Deduplication:" in rendered
    assert "incoming_batch" in rendered
    assert "replaced_existing" in rendered
    assert "storage/ingestion_staging/old/atlas.md" in rendered


def test_ingestion_view_formats_short_deduplication_path_summary() -> None:
    """Build a concise path summary for the ingestion status card."""
    summary = IngestionView._format_deduplication_paths(
        {
            "incoming_batch": {
                "kept_paths": [
                    "storage/ingestion_staging/new/atlas.md",
                    "storage/ingestion_staging/new/policy.md",
                    "storage/ingestion_staging/new/extra.md",
                ]
            },
            "replaced_existing": {
                "replaced_paths": [
                    "storage/ingestion_staging/old/atlas.md",
                ]
            },
        }
    )

    assert "conservados:" in summary
    assert "reemplazados:" in summary
    assert "(+1)" in summary


def test_ingestion_view_toggles_raw_output_visibility() -> None:
    """Allow users to hide technical timeline while keeping summary visible."""
    view = _build_view()

    view._toggle_raw_output(False)
    assert view.output.isHidden()

    view._toggle_raw_output(True)
    assert not view.output.isHidden()


def test_ingestion_view_mode_selector_defaults_to_async() -> None:
    """Expose explicit ingestion mode selector with async as default."""
    view = _build_view()

    assert str(view.execution_mode.currentData()) == "async"
    assert view.execution_mode.count() == 2


def test_ingestion_view_async_readiness_helpers() -> None:
    """Format readiness payload and detect not-ready async conditions."""
    payload = {
        "ready": False,
        "recommendation": "sync",
        "checks": {
            "redis": {
                "required": True,
                "ok": False,
                "detail": "connection refused",
            }
        },
    }

    assert IngestionView._is_async_ready(payload) is False
    rendered = IngestionView._format_async_readiness(payload)
    assert "recommendation: sync" in rendered
    assert "redis" in rendered


def test_ingestion_view_deletes_document_by_id_and_renders_summary() -> None:
    """Run one-document delete flow from Ingestion and render its result."""
    view = _build_view()
    view.delete_document_id.setText("doc-123")

    with patch(
        "coderag.ui.ingestion_view.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    ):
        view._run_delete_document()

    summary = view.summary.toPlainText()
    assert "Estado: completado" in summary
    assert "Document ID: doc-123" in summary
    assert "Documentos eliminados: 1" in summary
    assert view.progress.value() == 100
    assert view.delete_document_id.text() == ""


def test_ingestion_view_delete_button_requires_document_id() -> None:
    """Keep point delete disabled until a document id is provided."""
    view = _build_view()

    assert view.delete_document_button.isEnabled() is False

    view.delete_document_id.setText("doc-1")
    assert view.delete_document_button.isEnabled() is True
