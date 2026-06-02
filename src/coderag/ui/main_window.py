"""Main desktop window combining ingestion and query views."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout

from coderag.core.settings import get_settings
from coderag.ui.api_client import UiApiClient, _collect_upload_entries
from coderag.ui.ingestion_view import IngestionView
from coderag.ui.query_view import QueryView
from coderag.ui.tdm_view import TdmView
from coderag.ui.theme import build_stylesheet


def _collect_upload_file_paths(local_path_raw: str) -> list[Path]:
    """Expand local file or directory inputs into supported upload files."""
    return [item[0] for item in _collect_upload_entries(local_path_raw)]


class MainWindow(QMainWindow):
    """Main UI shell for the RAG Hybrid Response Validator."""

    def __init__(self, api_base_url: str = "http://127.0.0.1:8000") -> None:
        super().__init__()
        self.api_base_url = api_base_url.rstrip("/")
        self.api_client = UiApiClient(api_base_url=self.api_base_url)
        self.setWindowTitle("RAG Hybrid Response Validator")
        self.resize(1100, 760)

        self.setStyleSheet(build_stylesheet())

        tabs = QTabWidget()
        tabs.addTab(
            IngestionView(
                self.ingest,
                self.reset_all,
                on_delete_document=self.delete_document,
                on_ingestion_readiness=self.ingest_readiness,
            ),
            "Ingestion",
        )
        tabs.addTab(
            QueryView(
                self.query,
                self.list_documents,
                on_delete_document=self.delete_document,
                on_list_document_tags=self.list_document_tags,
                on_replace_document_tags=self.replace_document_tags,
            ),
            "Query",
        )
        tabs.addTab(
            TdmView(
                on_tdm_ingest=self.tdm_ingest,
                on_tdm_query=self.tdm_query,
                on_tdm_service_catalog=self.tdm_service_catalog,
                on_tdm_table_catalog=self.tdm_table_catalog,
                on_tdm_virtualization_preview=self.tdm_virtualization_preview,
                on_tdm_synthetic_profile=self.tdm_synthetic_profile,
            ),
            "TDM",
        )

        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(14, 14, 14, 14)
        shell_layout.addWidget(tabs)
        self.setCentralWidget(shell)

    def ingest(
        self,
        payload: dict[str, Any],
        on_update: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Run ingestion in selected mode and poll when async is used."""
        api_client = getattr(self, "api_client", None)
        if api_client is not None:
            return api_client.ingest(payload, on_update=on_update)

        source = payload.get("source")
        source_type = ""
        if isinstance(source, dict):
            source_type = str(source.get("source_type", "")).strip().lower()

        if source_type == "folder":
            return self._ingest_via_upload(payload, on_update=on_update)

        ingestion_channel = str(
            payload.get("_ingestion_channel", "json_folder")
        ).strip().lower()
        if ingestion_channel == "upload_file":
            return self._ingest_via_upload(payload, on_update=on_update)

        candidate_payload = dict(payload)
        execution_mode = str(
            candidate_payload.pop("_ingestion_mode", "async")
        ).strip().lower()
        if execution_mode not in {"async", "sync"}:
            execution_mode = "async"

        if execution_mode == "sync":
            return self._post_json("/sources/ingest", candidate_payload, timeout=3600)
        return self._post_json("/sources/ingest/async", candidate_payload, timeout=15)

    def ingest_readiness(self) -> dict[str, Any]:
        """Fetch operational readiness details for async ingestion mode."""
        return self.api_client.ingest_readiness()

    def query(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Call backend query endpoint."""
        return self.api_client.query(payload)

    def list_documents(
        self,
        source_id: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch ingested document catalog for optional source filter."""
        return self.api_client.list_documents(source_id=source_id, tags=tags)

    def list_document_tags(
        self,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        """Fetch aggregated tag facets for optional source filter."""
        return self.api_client.list_document_tags(source_id=source_id)

    def delete_document(self, document_id: str) -> dict[str, Any]:
        """Delete one persisted document from the backend catalog."""
        return self.api_client.delete_document(document_id)

    def replace_document_tags(
        self,
        document_id: str,
        tags: list[str],
    ) -> dict[str, Any]:
        """Replace the persisted tags for one document."""
        return self.api_client.replace_document_tags(document_id, tags)

    def reset_all(self) -> dict[str, Any]:
        """Call backend endpoint to clear all repositories and indexes."""
        admin_reset_token = (get_settings().admin_reset_token or "").strip()
        if not admin_reset_token:
            return {
                "status": "failed",
                "message": "ADMIN_RESET_TOKEN no está configurado para la UI.",
            }
        return self.api_client.reset_all(admin_reset_token=admin_reset_token)

    def tdm_ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Call backend TDM ingest endpoint."""
        api_client = getattr(self, "api_client", None)
        if api_client is not None:
            return api_client.tdm_ingest(payload)
        return self._post_json("/tdm/ingest", payload, timeout=3600)

    def tdm_query(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Call backend TDM query endpoint."""
        api_client = getattr(self, "api_client", None)
        if api_client is not None:
            return api_client.tdm_query(payload)
        return self._post_json("/tdm/query", payload, timeout=180)

    def tdm_service_catalog(
        self,
        service_name: str,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        """Fetch TDM service catalog by service name."""
        api_client = getattr(self, "api_client", None)
        if api_client is not None:
            return api_client.tdm_service_catalog(
                service_name=service_name,
                source_id=source_id,
            )

        path = f"/tdm/catalog/services/{service_name}"
        if source_id:
            path = f"{path}?source_id={source_id}"
        return self._get_json(path, timeout=60)

    def tdm_table_catalog(
        self,
        table_name: str,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        """Fetch TDM table catalog by table name."""
        api_client = getattr(self, "api_client", None)
        if api_client is not None:
            return api_client.tdm_table_catalog(
                table_name=table_name,
                source_id=source_id,
            )

        path = f"/tdm/catalog/tables/{table_name}"
        if source_id:
            path = f"{path}?source_id={source_id}"
        return self._get_json(path, timeout=60)

    def tdm_virtualization_preview(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Call backend TDM virtualization preview endpoint."""
        api_client = getattr(self, "api_client", None)
        if api_client is not None:
            return api_client.tdm_virtualization_preview(payload)
        return self._post_json("/tdm/virtualization/preview", payload, timeout=180)

    def tdm_synthetic_profile(
        self,
        table_name: str,
        source_id: str | None = None,
        target_rows: int = 1000,
    ) -> dict[str, Any]:
        """Fetch synthetic profile plan for one table."""
        api_client = getattr(self, "api_client", None)
        if api_client is not None:
            return api_client.tdm_synthetic_profile(
                table_name=table_name,
                source_id=source_id,
                target_rows=target_rows,
            )

        path = f"/tdm/synthetic/profile/{table_name}?target_rows={max(1, int(target_rows))}"
        if source_id:
            path = f"{path}&source_id={source_id}"
        return self._get_json(path, timeout=120)

    def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        timeout: int,
    ) -> dict[str, Any]:
        """Delegate POST requests through the shared UI API client."""
        return self.api_client.post_json(path, payload, timeout)

    def _get_json(self, path: str, timeout: int) -> dict[str, Any]:
        """Delegate GET requests through the shared UI API client."""
        return self.api_client.get_json(path, timeout)

    def _ingest_via_upload(
        self,
        payload: dict[str, Any],
        on_update: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Delegate multipart upload ingestion through the shared UI API client."""
        return self.api_client._ingest_via_upload(payload, on_update=on_update)


def launch_ui(api_base_url: str = "http://127.0.0.1:8000") -> None:
    """Start Qt application."""
    app = QApplication(sys.argv)
    app.setApplicationName("RAG Hybrid Response Validator")
    window = MainWindow(api_base_url=api_base_url)
    window.show()
    app.exec()
