"""UI shell tests for additive TDM endpoint wiring in MainWindow."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from typing import Any

from coderag.ui.main_window import MainWindow


def _build_lightweight_window() -> MainWindow:
    """Create a non-Qt-initialized MainWindow instance for method tests."""
    window = MainWindow.__new__(MainWindow)
    window.api_base_url = "http://127.0.0.1:8000"
    return window


def test_main_window_tdm_post_endpoints_are_wired() -> None:
    """Route TDM POST callbacks to expected backend paths."""
    window = _build_lightweight_window()

    captured: list[tuple[str, dict[str, Any], int]] = []

    def _fake_post(path: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
        captured.append((path, payload, timeout))
        return {"status": "ok", "path": path}

    window._post_json = _fake_post  # type: ignore[method-assign]

    ingest_payload = {
        "source": {"source_type": "tdm_folder", "local_path": "sample_data", "filters": {}}
    }
    query_payload = {"question": "que tablas usa billing-api"}

    ingest_result = window.tdm_ingest(ingest_payload)
    query_result = window.tdm_query(query_payload)
    preview_result = window.tdm_virtualization_preview(query_payload)

    assert ingest_result["path"] == "/tdm/ingest"
    assert query_result["path"] == "/tdm/query"
    assert preview_result["path"] == "/tdm/virtualization/preview"
    assert captured[0][0] == "/tdm/ingest"
    assert captured[1][0] == "/tdm/query"
    assert captured[2][0] == "/tdm/virtualization/preview"


def test_main_window_tdm_get_endpoints_build_expected_paths() -> None:
    """Build TDM catalog and synthetic GET routes with query params."""
    window = _build_lightweight_window()

    captured: list[tuple[str, int]] = []

    def _fake_get(path: str, timeout: int) -> dict[str, Any]:
        captured.append((path, timeout))
        return {"status": "ok", "path": path}

    window._get_json = _fake_get  # type: ignore[method-assign]

    service_result = window.tdm_service_catalog("billing-api", "src-1")
    table_result = window.tdm_table_catalog("invoices", None)
    synthetic_result = window.tdm_synthetic_profile(
        "invoices",
        "src-1",
        200,
    )

    assert service_result["path"] == "/tdm/catalog/services/billing-api?source_id=src-1"
    assert table_result["path"] == "/tdm/catalog/tables/invoices"
    assert synthetic_result["path"] == "/tdm/synthetic/profile/invoices?target_rows=200&source_id=src-1"
    assert captured[0][0].startswith("/tdm/catalog/services/")
    assert captured[1][0] == "/tdm/catalog/tables/invoices"
    assert "target_rows=200" in captured[2][0]
