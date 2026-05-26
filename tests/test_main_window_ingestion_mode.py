"""Tests for MainWindow delegation to UiApiClient."""

from __future__ import annotations

from typing import Any

from coderag.ui.main_window import MainWindow


class _FakeApiClient:
    """Minimal fake API client used to assert MainWindow delegation."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def ingest(self, payload: dict[str, Any], on_update=None) -> dict[str, Any]:
        self.calls.append(("ingest", (payload, on_update), {}))
        return {"status": "completed", "job_id": "job-1"}

    def ingest_readiness(self) -> dict[str, Any]:
        self.calls.append(("ingest_readiness", (), {}))
        return {"ready": True}

    def list_documents(
        self,
        source_id: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(("list_documents", (), {"source_id": source_id, "tags": tags}))
        return {"count": 0, "documents": []}

    def list_document_tags(self, source_id: str | None = None) -> dict[str, Any]:
        self.calls.append(("list_document_tags", (), {"source_id": source_id}))
        return {"count": 0, "items": []}

    def delete_document(self, document_id: str) -> dict[str, Any]:
        self.calls.append(("delete_document", (), {"document_id": document_id}))
        return {"status": "completed"}

    def replace_document_tags(self, document_id: str, tags: list[str]) -> dict[str, Any]:
        self.calls.append(
            ("replace_document_tags", (), {"document_id": document_id, "tags": tags})
        )
        return {"status": "updated", "new_tags": tags}

    def reset_all(self) -> dict[str, Any]:
        self.calls.append(("reset_all", (), {}))
        return {"status": "completed"}

    def tdm_ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("tdm_ingest", (payload,), {}))
        return {"status": "completed"}

    def tdm_query(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("tdm_query", (payload,), {}))
        return {"status": "completed"}

    def tdm_service_catalog(
        self,
        service_name: str,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "tdm_service_catalog",
                (),
                {"service_name": service_name, "source_id": source_id},
            )
        )
        return {"count": 0}

    def tdm_table_catalog(
        self,
        table_name: str,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "tdm_table_catalog",
                (),
                {"table_name": table_name, "source_id": source_id},
            )
        )
        return {"count": 0}

    def tdm_virtualization_preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("tdm_virtualization_preview", (payload,), {}))
        return {"count": 0}

    def tdm_synthetic_profile(
        self,
        table_name: str,
        source_id: str | None = None,
        target_rows: int = 1000,
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "tdm_synthetic_profile",
                (),
                {
                    "table_name": table_name,
                    "source_id": source_id,
                    "target_rows": target_rows,
                },
            )
        )
        return {"profile_id": "syn-1"}


def _build_lightweight_window() -> MainWindow:
    """Create a non-Qt-initialized MainWindow instance for method tests."""
    window = MainWindow.__new__(MainWindow)
    window.api_base_url = "http://127.0.0.1:8000"
    window.api_client = _FakeApiClient()
    return window


def test_main_window_ingest_delegates_to_api_client() -> None:
    """Delegate ingestion execution to UiApiClient abstraction."""
    window = _build_lightweight_window()

    result = window.ingest({"_ingestion_mode": "async", "source": {"source_type": "folder"}})

    assert result["status"] == "completed"
    assert window.api_client.calls[0][0] == "ingest"


def test_main_window_ingest_readiness_delegates_to_api_client() -> None:
    """Delegate readiness check to UiApiClient abstraction."""
    window = _build_lightweight_window()

    result = window.ingest_readiness()

    assert result["ready"] is True
    assert window.api_client.calls[0][0] == "ingest_readiness"


def test_main_window_list_documents_delegates_with_args() -> None:
    """Delegate catalog listing with source and tags filters."""
    window = _build_lightweight_window()

    result = window.list_documents("src-1", ["finance", "urgent"])

    assert result["count"] == 0
    assert window.api_client.calls[0] == (
        "list_documents",
        (),
        {"source_id": "src-1", "tags": ["finance", "urgent"]},
    )


def test_main_window_replace_document_tags_delegates() -> None:
    """Delegate tag replacement through UiApiClient."""
    window = _build_lightweight_window()

    result = window.replace_document_tags("doc-1", ["legal", "approved"])

    assert result["status"] == "updated"
    assert window.api_client.calls[0] == (
        "replace_document_tags",
        (),
        {"document_id": "doc-1", "tags": ["legal", "approved"]},
    )


def test_main_window_tdm_methods_delegate_to_api_client() -> None:
    """Delegate all TDM operations through UiApiClient façade."""
    window = _build_lightweight_window()

    window.tdm_ingest({"source": {"source_type": "tdm_folder"}})
    window.tdm_query({"question": "impacto"})
    window.tdm_service_catalog("billing-api", "src-1")
    window.tdm_table_catalog("invoices", "src-1")
    window.tdm_virtualization_preview({"question": "preview"})
    result = window.tdm_synthetic_profile("invoices", "src-1", 500)

    assert result["profile_id"] == "syn-1"
    method_names = [item[0] for item in window.api_client.calls]
    assert method_names == [
        "tdm_ingest",
        "tdm_query",
        "tdm_service_catalog",
        "tdm_table_catalog",
        "tdm_virtualization_preview",
        "tdm_synthetic_profile",
    ]
