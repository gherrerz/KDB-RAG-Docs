"""Ingestion panel for source configuration and indexing."""

from __future__ import annotations

import json
from typing import Callable

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class IngestionView(QWidget):
    """Widget for invoking source ingestion via callback."""

    def __init__(self, on_ingest: Callable[[dict], dict]) -> None:
        super().__init__()
        self._on_ingest = on_ingest

        layout = QVBoxLayout(self)
        form_group = QGroupBox("Source Configuration")
        form_layout = QFormLayout(form_group)

        self.source_type = QLineEdit("folder")
        self.local_path = QLineEdit("sample_data")
        self.base_url = QLineEdit()
        self.token = QLineEdit()
        self.filters = QLineEdit("{}")

        form_layout.addRow("Source Type", self.source_type)
        form_layout.addRow("Local Path", self.local_path)
        form_layout.addRow("Base URL", self.base_url)
        form_layout.addRow("Token", self.token)
        form_layout.addRow("Filters (JSON)", self.filters)

        actions = QHBoxLayout()
        self.ingest_button = QPushButton("Ingest")
        self.ingest_button.clicked.connect(self._run_ingestion)
        actions.addWidget(self.ingest_button)
        actions.addWidget(QLabel("Indexes chunks + graph + retrieval."))

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        layout.addWidget(form_group)
        layout.addLayout(actions)
        layout.addWidget(self.output)

    def _run_ingestion(self) -> None:
        payload = {
            "source": {
                "source_type": self.source_type.text().strip() or "folder",
                "local_path": self.local_path.text().strip() or None,
                "base_url": self.base_url.text().strip() or None,
                "token": self.token.text().strip() or None,
                "filters": self._safe_json(self.filters.text().strip()),
            }
        }
        result = self._on_ingest(payload)
        self.output.setPlainText(
            json.dumps(result, indent=2, ensure_ascii=False)
        )

    @staticmethod
    def _safe_json(raw: str) -> dict:
        if not raw:
            return {}
        try:
            value = json.loads(raw)
            if isinstance(value, dict):
                return value
            return {}
        except json.JSONDecodeError:
            return {}
