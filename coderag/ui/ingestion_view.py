"""Ingestion panel for source configuration and indexing."""

from __future__ import annotations

import json
from typing import Callable

from PySide6.QtWidgets import (
    QApplication,
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
        self.output.setPlainText("Ingestion running...\n")
        QApplication.processEvents()
        result = self._on_ingest(payload)
        rendered = self._format_ingestion_result(result)
        self.output.setPlainText(rendered)

    @staticmethod
    def _format_ingestion_result(result: dict) -> str:
        """Return a readable ingestion trace for the UI text panel."""
        lines: list[str] = []

        status = str(result.get("status", "unknown"))
        lines.append(f"Status: {status}")

        message = result.get("message")
        if isinstance(message, str) and message.strip():
            lines.append(f"Message: {message}")

        source_id = result.get("source_id")
        if isinstance(source_id, str) and source_id:
            lines.append(f"Source ID: {source_id}")

        documents = result.get("documents")
        chunks = result.get("chunks")
        if documents is not None and chunks is not None:
            lines.append(f"Documents: {documents} | Chunks: {chunks}")

        metrics = result.get("metrics")
        if isinstance(metrics, dict) and metrics:
            lines.append("\nMetrics:")
            for key, value in metrics.items():
                lines.append(f"- {key}: {value}")

        steps = result.get("steps")
        if isinstance(steps, list) and steps:
            lines.append("\nIngestion Trace:")
            for index, step in enumerate(steps, start=1):
                if not isinstance(step, dict):
                    continue
                name = str(step.get("name", "step"))
                step_status = str(step.get("status", "ok"))
                lines.append(f"{index}. [{step_status}] {name}")
                details = step.get("details", {})
                if isinstance(details, dict):
                    for key, value in details.items():
                        lines.append(f"   - {key}: {value}")

        lines.append("\nRaw JSON:")
        lines.append(json.dumps(result, indent=2, ensure_ascii=False))
        return "\n".join(lines)

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
