"""Main desktop window combining ingestion and query views."""

from __future__ import annotations

import sys
from typing import Any, Dict

import requests
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget

from coderag.ui.ingestion_view import IngestionView
from coderag.ui.query_view import QueryView


class MainWindow(QMainWindow):
    """Main UI shell for the RAG Hybrid Response Validator."""

    def __init__(self, api_base_url: str = "http://127.0.0.1:8000") -> None:
        super().__init__()
        self.api_base_url = api_base_url.rstrip("/")
        self.setWindowTitle("RAG Hybrid Response Validator")
        self.resize(1100, 760)

        tabs = QTabWidget()
        tabs.addTab(IngestionView(self.ingest), "Ingestion")
        tabs.addTab(QueryView(self.query), "Query")
        self.setCentralWidget(tabs)

    def ingest(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Call backend ingestion endpoint."""
        return self._post_json("/sources/ingest", payload)

    def query(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Call backend query endpoint."""
        return self._post_json("/query", payload)

    def _post_json(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            response = requests.post(
                f"{self.api_base_url}{path}",
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            return {"error": str(exc)}


def launch_ui(api_base_url: str = "http://127.0.0.1:8000") -> None:
    """Start Qt application."""
    app = QApplication(sys.argv)
    window = MainWindow(api_base_url=api_base_url)
    window.show()
    app.exec()
