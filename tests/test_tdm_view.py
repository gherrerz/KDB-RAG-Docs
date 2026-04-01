"""UI tests for TDM view payload wiring and disabled-state messaging."""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from coderag.ui.tdm_view import TdmView


def _ensure_app() -> QApplication:
    """Return QApplication instance for widget tests."""
    app = QApplication.instance()
    if app is not None:
        return app
    return QApplication([])


def test_tdm_view_builds_query_payload_from_inputs() -> None:
    """Send TDM query payload with expected optional fields."""
    _ensure_app()
    captured_payload: dict[str, Any] = {}

    def _on_tdm_query(payload: dict[str, Any]) -> dict[str, Any]:
        captured_payload.update(payload)
        return {"answer": "ok", "findings": [], "diagnostics": {}}

    view = TdmView(
        on_tdm_ingest=lambda payload: {"status": "completed"},
        on_tdm_query=_on_tdm_query,
        on_tdm_service_catalog=lambda service_name, source_id: {"count": 0},
        on_tdm_table_catalog=lambda table_name, source_id: {"count": 0},
        on_tdm_virtualization_preview=lambda payload: {"count": 0},
        on_tdm_synthetic_profile=lambda table_name, source_id, rows: {"profile_id": "syn-1"},
    )

    view.question.setText("que tablas usa billing-api")
    view.source_id.setText("src-1")
    view.service_name.setText("billing-api")
    view.table_name.setText("invoices")
    view.include_virtualization_preview.setChecked(True)

    view._run_tdm_query()

    assert captured_payload["question"] == "que tablas usa billing-api"
    assert captured_payload["source_id"] == "src-1"
    assert captured_payload["service_name"] == "billing-api"
    assert captured_payload["table_name"] == "invoices"
    assert captured_payload["include_virtualization_preview"] is True
    view.close()


def test_tdm_view_shows_explicit_message_when_tdm_is_disabled() -> None:
    """Render explicit guidance when backend responds with TDM disabled."""
    _ensure_app()

    view = TdmView(
        on_tdm_ingest=lambda payload: {
            "detail": "TDM endpoints are disabled.",
            "error": "404 Client Error",
        },
        on_tdm_query=lambda payload: {"answer": "ok", "findings": [], "diagnostics": {}},
        on_tdm_service_catalog=lambda service_name, source_id: {"count": 0},
        on_tdm_table_catalog=lambda table_name, source_id: {"count": 0},
        on_tdm_virtualization_preview=lambda payload: {"count": 0},
        on_tdm_synthetic_profile=lambda table_name, source_id, rows: {"profile_id": "syn-1"},
    )

    view.local_path.setText("sample_data")
    view._run_tdm_ingest()

    summary = view.summary.toPlainText().lower()
    hint = view.status_hint.text().lower()
    assert "tdm deshabilitado" in hint
    assert "failed" in summary
    view.close()


def test_tdm_view_shows_service_unavailable_hint_for_503_errors() -> None:
    """Map backend 503 failures into an actionable status hint."""
    _ensure_app()

    view = TdmView(
        on_tdm_ingest=lambda payload: {"status": "completed"},
        on_tdm_query=lambda payload: {
            "detail": "503 Service Unavailable",
            "error": "503 Client Error",
        },
        on_tdm_service_catalog=lambda service_name, source_id: {"count": 0},
        on_tdm_table_catalog=lambda table_name, source_id: {"count": 0},
        on_tdm_virtualization_preview=lambda payload: {"count": 0},
        on_tdm_synthetic_profile=lambda table_name, source_id, rows: {"profile_id": "syn-1"},
    )

    view.question.setText("impacto de billing")
    view._run_tdm_query()

    hint = view.status_hint.text().lower()
    assert "503" in hint
    view.close()


def test_tdm_view_shows_empty_result_hint_for_zero_findings() -> None:
    """Guide users when operation succeeds but returns no findings."""
    _ensure_app()

    view = TdmView(
        on_tdm_ingest=lambda payload: {"status": "completed"},
        on_tdm_query=lambda payload: {
            "answer": "ok",
            "findings": [],
            "count": 0,
            "diagnostics": {},
        },
        on_tdm_service_catalog=lambda service_name, source_id: {"count": 0},
        on_tdm_table_catalog=lambda table_name, source_id: {"count": 0},
        on_tdm_virtualization_preview=lambda payload: {"count": 0},
        on_tdm_synthetic_profile=lambda table_name, source_id, rows: {"profile_id": "syn-1"},
    )

    view.question.setText("servicio inexistente")
    view._run_tdm_query()

    hint = view.status_hint.text().lower()
    assert "sin resultados" in hint
    assert "completed" in view.summary.toPlainText().lower()
    view.close()


def test_tdm_view_renders_structured_rows_for_findings() -> None:
    """Render findings into table rows for operational review."""
    _ensure_app()

    view = TdmView(
        on_tdm_ingest=lambda payload: {"status": "completed"},
        on_tdm_query=lambda payload: {
            "answer": "ok",
            "findings": [
                {
                    "service_name": "billing-api",
                    "endpoint": "/v1/invoices",
                    "method": "GET",
                }
            ],
            "diagnostics": {},
        },
        on_tdm_service_catalog=lambda service_name, source_id: {"count": 0},
        on_tdm_table_catalog=lambda table_name, source_id: {"count": 0},
        on_tdm_virtualization_preview=lambda payload: {"count": 0},
        on_tdm_synthetic_profile=lambda table_name, source_id, rows: {"profile_id": "syn-1"},
    )

    view.question.setText("que usa billing")
    view._run_tdm_query()

    assert view.result_table.rowCount() == 1
    assert view.result_table.item(0, 0).text() == "finding"
    assert view.result_table.item(0, 1).text() == "billing-api"
    view.close()


def test_tdm_view_renders_detail_for_selected_result_row() -> None:
    """Show JSON detail panel from selected structured row."""
    _ensure_app()

    view = TdmView(
        on_tdm_ingest=lambda payload: {"status": "completed"},
        on_tdm_query=lambda payload: {
            "answer": "ok",
            "findings": [
                {
                    "service_name": "billing-api",
                    "endpoint": "/v1/invoices",
                    "method": "GET",
                }
            ],
            "diagnostics": {},
        },
        on_tdm_service_catalog=lambda service_name, source_id: {"count": 0},
        on_tdm_table_catalog=lambda table_name, source_id: {"count": 0},
        on_tdm_virtualization_preview=lambda payload: {"count": 0},
        on_tdm_synthetic_profile=lambda table_name, source_id, rows: {"profile_id": "syn-1"},
    )

    view.question.setText("que usa billing")
    view._run_tdm_query()
    view.result_table.selectRow(0)
    view._render_selected_result_detail()

    detail = view.result_detail.toPlainText()
    assert "billing-api" in detail
    assert "/v1/invoices" in detail
    view.close()


def test_tdm_view_filters_structured_rows_by_keyword() -> None:
    """Filter result table rows using keyword across visible columns."""
    _ensure_app()

    view = TdmView(
        on_tdm_ingest=lambda payload: {"status": "completed"},
        on_tdm_query=lambda payload: {
            "answer": "ok",
            "findings": [
                {"service_name": "billing-api", "endpoint": "/v1/invoices", "method": "GET"},
                {"service_name": "inventory-api", "endpoint": "/v1/items", "method": "POST"},
            ],
            "diagnostics": {},
        },
        on_tdm_service_catalog=lambda service_name, source_id: {"count": 0},
        on_tdm_table_catalog=lambda table_name, source_id: {"count": 0},
        on_tdm_virtualization_preview=lambda payload: {"count": 0},
        on_tdm_synthetic_profile=lambda table_name, source_id, rows: {"profile_id": "syn-1"},
    )

    view.question.setText("listar servicios")
    view._run_tdm_query()
    assert view.result_table.rowCount() == 2

    view.result_filter.setText("inventory")
    assert view.result_table.rowCount() == 1
    assert view.result_table.item(0, 1).text() == "inventory-api"
    assert "1 fila" in view.result_count_label.text()
    view.close()


def test_tdm_view_exports_visible_rows_to_raw_panel() -> None:
    """Export currently visible rows to raw JSON panel for quick sharing."""
    _ensure_app()

    view = TdmView(
        on_tdm_ingest=lambda payload: {"status": "completed"},
        on_tdm_query=lambda payload: {
            "answer": "ok",
            "findings": [
                {"service_name": "billing-api", "endpoint": "/v1/invoices", "method": "GET"},
            ],
            "diagnostics": {},
        },
        on_tdm_service_catalog=lambda service_name, source_id: {"count": 0},
        on_tdm_table_catalog=lambda table_name, source_id: {"count": 0},
        on_tdm_virtualization_preview=lambda payload: {"count": 0},
        on_tdm_synthetic_profile=lambda table_name, source_id, rows: {"profile_id": "syn-1"},
    )

    view.question.setText("listar servicios")
    view._run_tdm_query()
    view._export_visible_rows_to_raw()

    raw_text = view.raw.toPlainText()
    assert "tdm_visible_rows" in raw_text
    assert "billing-api" in raw_text
    assert "exportadas" in view.status_hint.text().lower()
    view.close()


def test_tdm_view_filters_rows_by_selected_type() -> None:
    """Filter visible rows by structured result type selector."""
    _ensure_app()

    view = TdmView(
        on_tdm_ingest=lambda payload: {"status": "completed"},
        on_tdm_query=lambda payload: {
            "answer": "ok",
            "findings": [
                {"service_name": "billing-api", "endpoint": "/v1/invoices", "method": "GET"},
            ],
            "diagnostics": {},
        },
        on_tdm_service_catalog=lambda service_name, source_id: {
            "mappings": [
                {"service_name": "inventory-api", "endpoint": "/v1/items", "method": "POST"}
            ],
            "count": 1,
        },
        on_tdm_table_catalog=lambda table_name, source_id: {"count": 0},
        on_tdm_virtualization_preview=lambda payload: {"count": 0},
        on_tdm_synthetic_profile=lambda table_name, source_id, rows: {"profile_id": "syn-1"},
    )

    view.question.setText("listar servicios")
    view._run_tdm_query()
    assert view.result_table.rowCount() == 1
    assert view.result_type_filter.count() >= 2

    view.service_name.setText("inventory-api")
    view._run_service_catalog()
    assert view.result_table.rowCount() == 1

    type_index = -1
    for idx in range(view.result_type_filter.count()):
        if str(view.result_type_filter.itemData(idx) or "") == "service_mapping":
            type_index = idx
            break
    assert type_index >= 0

    view.result_type_filter.setCurrentIndex(type_index)
    assert view.result_table.rowCount() == 1
    assert view.result_table.item(0, 0).text() == "service_mapping"
    view.close()


def test_tdm_view_combines_type_and_text_filters() -> None:
    """Apply type selector and text filter together for narrowing results."""
    _ensure_app()

    view = TdmView(
        on_tdm_ingest=lambda payload: {"status": "completed"},
        on_tdm_query=lambda payload: {
            "answer": "ok",
            "findings": [
                {"service_name": "billing-api", "endpoint": "/v1/invoices", "method": "GET"},
                {"service_name": "inventory-api", "endpoint": "/v1/items", "method": "POST"},
            ],
            "diagnostics": {},
        },
        on_tdm_service_catalog=lambda service_name, source_id: {"count": 0},
        on_tdm_table_catalog=lambda table_name, source_id: {"count": 0},
        on_tdm_virtualization_preview=lambda payload: {"count": 0},
        on_tdm_synthetic_profile=lambda table_name, source_id, rows: {"profile_id": "syn-1"},
    )

    view.question.setText("listar servicios")
    view._run_tdm_query()
    assert view.result_table.rowCount() == 2

    type_index = -1
    for idx in range(view.result_type_filter.count()):
        if str(view.result_type_filter.itemData(idx) or "") == "finding":
            type_index = idx
            break
    assert type_index >= 0

    view.result_type_filter.setCurrentIndex(type_index)
    view.result_filter.setText("inventory")
    assert view.result_table.rowCount() == 1
    assert view.result_table.item(0, 1).text() == "inventory-api"
    view.close()


def test_tdm_view_copies_selected_row_json_to_clipboard() -> None:
    """Copy selected structured row JSON for quick handoff."""
    app = _ensure_app()

    view = TdmView(
        on_tdm_ingest=lambda payload: {"status": "completed"},
        on_tdm_query=lambda payload: {
            "answer": "ok",
            "findings": [
                {"service_name": "billing-api", "endpoint": "/v1/invoices", "method": "GET"},
            ],
            "diagnostics": {},
        },
        on_tdm_service_catalog=lambda service_name, source_id: {"count": 0},
        on_tdm_table_catalog=lambda table_name, source_id: {"count": 0},
        on_tdm_virtualization_preview=lambda payload: {"count": 0},
        on_tdm_synthetic_profile=lambda table_name, source_id, rows: {"profile_id": "syn-1"},
    )

    view.question.setText("listar")
    view._run_tdm_query()
    view.result_table.selectRow(0)
    view._copy_selected_row_json()

    clipboard_text = app.clipboard().text()
    assert "billing-api" in clipboard_text
    assert "endpoint" in clipboard_text
    view.close()


def test_tdm_view_copies_selected_endpoint_method_to_clipboard() -> None:
    """Copy endpoint and HTTP method from selected row payload."""
    app = _ensure_app()

    view = TdmView(
        on_tdm_ingest=lambda payload: {"status": "completed"},
        on_tdm_query=lambda payload: {
            "answer": "ok",
            "findings": [
                {"service_name": "billing-api", "endpoint": "/v1/invoices", "method": "GET"},
            ],
            "diagnostics": {},
        },
        on_tdm_service_catalog=lambda service_name, source_id: {"count": 0},
        on_tdm_table_catalog=lambda table_name, source_id: {"count": 0},
        on_tdm_virtualization_preview=lambda payload: {"count": 0},
        on_tdm_synthetic_profile=lambda table_name, source_id, rows: {"profile_id": "syn-1"},
    )

    view.question.setText("listar")
    view._run_tdm_query()
    view.result_table.selectRow(0)
    view._copy_selected_endpoint_method()

    clipboard_text = app.clipboard().text()
    assert clipboard_text == "GET /v1/invoices"
    view.close()


def test_tdm_view_loads_selected_row_into_raw_panel() -> None:
    """Load selected row payload into raw panel for compact inspection."""
    _ensure_app()

    view = TdmView(
        on_tdm_ingest=lambda payload: {"status": "completed"},
        on_tdm_query=lambda payload: {
            "answer": "ok",
            "findings": [
                {"service_name": "billing-api", "endpoint": "/v1/invoices", "method": "GET"},
            ],
            "diagnostics": {},
        },
        on_tdm_service_catalog=lambda service_name, source_id: {"count": 0},
        on_tdm_table_catalog=lambda table_name, source_id: {"count": 0},
        on_tdm_virtualization_preview=lambda payload: {"count": 0},
        on_tdm_synthetic_profile=lambda table_name, source_id, rows: {"profile_id": "syn-1"},
    )

    view.question.setText("listar")
    view._run_tdm_query()
    view.result_table.selectRow(0)
    view._load_selected_row_raw()

    raw_text = view.raw.toPlainText()
    assert "billing-api" in raw_text
    assert "cargada" in view.status_hint.text().lower()
    view.close()


def test_tdm_view_shortcuts_trigger_quick_actions() -> None:
    """Trigger quick actions through keyboard shortcuts wiring."""
    app = _ensure_app()

    view = TdmView(
        on_tdm_ingest=lambda payload: {"status": "completed"},
        on_tdm_query=lambda payload: {
            "answer": "ok",
            "findings": [
                {"service_name": "billing-api", "endpoint": "/v1/invoices", "method": "GET"},
            ],
            "diagnostics": {},
        },
        on_tdm_service_catalog=lambda service_name, source_id: {"count": 0},
        on_tdm_table_catalog=lambda table_name, source_id: {"count": 0},
        on_tdm_virtualization_preview=lambda payload: {"count": 0},
        on_tdm_synthetic_profile=lambda table_name, source_id, rows: {"profile_id": "syn-1"},
    )

    view.question.setText("listar")
    view._run_tdm_query()
    view.result_table.selectRow(0)

    view._shortcuts["copy_endpoint"].activated.emit()
    assert app.clipboard().text() == "GET /v1/invoices"

    view._shortcuts["copy_row_json"].activated.emit()
    assert "billing-api" in app.clipboard().text()

    view._shortcuts["copy_endpoint"].activated.emit()
    assert app.clipboard().text() == "GET /v1/invoices"

    view._shortcuts["load_row_raw"].activated.emit()
    assert "billing-api" in view.raw.toPlainText()

    view._shortcuts["export_visible"].activated.emit()
    assert "tdm_visible_rows" in view.raw.toPlainText()

    view.close()


def test_tdm_view_shows_inline_shortcuts_hint() -> None:
    """Expose keyboard shortcuts in visible hint text for discoverability."""
    _ensure_app()

    view = TdmView(
        on_tdm_ingest=lambda payload: {"status": "completed"},
        on_tdm_query=lambda payload: {
            "answer": "ok",
            "findings": [],
            "diagnostics": {},
        },
        on_tdm_service_catalog=lambda service_name, source_id: {"count": 0},
        on_tdm_table_catalog=lambda table_name, source_id: {"count": 0},
        on_tdm_virtualization_preview=lambda payload: {"count": 0},
        on_tdm_synthetic_profile=lambda table_name, source_id, rows: {
            "profile_id": "syn-1"
        },
    )

    hint = view.shortcuts_hint.text().lower()
    assert "ctrl+shift+c" in hint
    assert "ctrl+shift+e" in hint
    assert "ctrl+shift+l" in hint
    assert "ctrl+shift+x" in hint
    view.close()
