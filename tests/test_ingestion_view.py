"""UI tests for ingestion form validation and progress rendering."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

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

    return IngestionView(_on_ingest, _on_reset_all)


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
        "steps": [{"elapsed_hhmmss": "00:01:12"}],
    }

    view._handle_live_update(result)

    assert view.progress.value() == 67
    summary = view.summary.toPlainText()
    assert "Estado: en curso" in summary
    assert "Documentos: 8" in summary
    assert "Chunks: 120" in summary


def test_ingestion_view_toggles_raw_output_visibility() -> None:
    """Allow users to hide technical timeline while keeping summary visible."""
    view = _build_view()

    view._toggle_raw_output(False)
    assert view.output.isHidden()

    view._toggle_raw_output(True)
    assert not view.output.isHidden()
