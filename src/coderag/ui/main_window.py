"""Main desktop window combining ingestion and query views."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout

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
        return self.api_client.ingest(payload, on_update=on_update)

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
        return self.api_client.reset_all()

    def tdm_ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Call backend TDM ingest endpoint."""
        return self.api_client.tdm_ingest(payload)

    def tdm_query(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Call backend TDM query endpoint."""
        return self.api_client.tdm_query(payload)

    def tdm_service_catalog(
        self,
        service_name: str,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        """Fetch TDM service catalog by service name."""
        return self.api_client.tdm_service_catalog(
            service_name=service_name,
            source_id=source_id,
        )

    def tdm_table_catalog(
        self,
        table_name: str,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        """Fetch TDM table catalog by table name."""
        return self.api_client.tdm_table_catalog(
            table_name=table_name,
            source_id=source_id,
        )

    def tdm_virtualization_preview(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Call backend TDM virtualization preview endpoint."""
        return self.api_client.tdm_virtualization_preview(payload)

    def tdm_synthetic_profile(
        self,
        table_name: str,
        source_id: str | None = None,
        target_rows: int = 1000,
    ) -> dict[str, Any]:
        """Fetch synthetic profile plan for one table."""
        return self.api_client.tdm_synthetic_profile(
            table_name=table_name,
            source_id=source_id,
            target_rows=target_rows,
        )


def launch_ui(api_base_url: str = "http://127.0.0.1:8000") -> None:
    """Start Qt application."""
    app = QApplication(sys.argv)
    app.setApplicationName("RAG Hybrid Response Validator")
    window = MainWindow(api_base_url=api_base_url)
    window.show()
    app.exec()
