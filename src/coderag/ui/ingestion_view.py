"""Ingestion panel for source configuration and indexing."""

from __future__ import annotations

import json
from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class _IngestionWorker(QObject):
    """Background worker that runs ingestion outside the UI thread."""

    progress = Signal(dict)
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        on_ingest: Callable[[dict, Callable[[dict], None] | None], dict],
        payload: dict,
    ) -> None:
        super().__init__()
        self._on_ingest = on_ingest
        self._payload = payload

    @Slot()
    def run(self) -> None:
        """Execute ingestion and emit progress/results safely."""
        try:
            result = self._on_ingest(self._payload, self._emit_progress)
        except Exception as exc:  # pragma: no cover - defensive UI guard
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)

    def _emit_progress(self, update: dict) -> None:
        """Forward live updates through Qt signals."""
        self.progress.emit(update)


class IngestionView(QWidget):
    """Widget for invoking source ingestion via callback."""

    def __init__(
        self,
        on_ingest: Callable[[dict, Callable[[dict], None] | None], dict],
        on_reset_all: Callable[[], dict],
    ) -> None:
        super().__init__()
        self._on_ingest = on_ingest
        self._on_reset_all = on_reset_all
        self._ingest_thread: QThread | None = None
        self._ingest_worker: _IngestionWorker | None = None

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
        self.reset_all_button = QPushButton("BORRAR TODO")
        self.reset_all_button.clicked.connect(self._run_reset_all)
        actions.addWidget(self.ingest_button)
        actions.addWidget(self.reset_all_button)
        actions.addWidget(QLabel("Indexes chunks + graph + retrieval."))

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        layout.addWidget(form_group)
        layout.addLayout(actions)
        layout.addWidget(self.output)

    def _run_ingestion(self) -> None:
        if self._ingest_thread is not None and self._ingest_thread.isRunning():
            self.output.setPlainText("Ingestion already running...\n")
            return

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
        self.ingest_button.setEnabled(False)
        self.reset_all_button.setEnabled(False)

        thread = QThread(self)
        worker = _IngestionWorker(self._on_ingest, payload)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self._handle_live_update)
        worker.finished.connect(self._handle_ingestion_finished)
        worker.failed.connect(self._handle_ingestion_failed)

        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_ingestion_thread_finished)

        self._ingest_thread = thread
        self._ingest_worker = worker
        thread.start()

    def _handle_live_update(self, result: dict) -> None:
        """Render incremental updates while ingestion is running."""
        rendered = self._format_ingestion_result(result)
        self.output.setPlainText(rendered)
        QApplication.processEvents()

    @Slot(dict)
    def _handle_ingestion_finished(self, result: dict) -> None:
        """Render final ingestion result and restore UI state."""
        rendered = self._format_ingestion_result(result)
        self.output.setPlainText(rendered)
        self.ingest_button.setEnabled(True)
        self.reset_all_button.setEnabled(True)

    @Slot(str)
    def _handle_ingestion_failed(self, error: str) -> None:
        """Render unexpected worker errors and restore UI state."""
        self.output.setPlainText(
            "Status: failed\n"
            f"Message: Unexpected ingestion error in UI worker: {error}"
        )
        self.ingest_button.setEnabled(True)
        self.reset_all_button.setEnabled(True)

    @Slot()
    def _on_ingestion_thread_finished(self) -> None:
        """Clear thread/worker refs after background ingestion exits."""
        self._ingest_thread = None
        self._ingest_worker = None

    def _run_reset_all(self) -> None:
        """Run destructive reset after explicit user confirmation."""
        decision = QMessageBox.question(
            self,
            "Confirmar borrado total",
            (
                "Esta accion borrara TODO: documentos, chunks, BM25, "
                "ChromaDB embebido, Neo4j y jobs historicos.\n\n"
                "Deseas continuar?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if decision != QMessageBox.StandardButton.Yes:
            self.output.setPlainText("Operacion cancelada por el usuario.")
            return

        self.output.setPlainText("Reset total en ejecucion...\n")
        QApplication.processEvents()
        result = self._on_reset_all()
        rendered = self._format_ingestion_result(result)
        self.output.setPlainText(rendered)

    @staticmethod
    def _format_ingestion_result(result: dict) -> str:
        """Return a readable ingestion trace for the UI text panel."""
        lines: list[str] = []

        status = str(result.get("status", "unknown"))
        lines.append(f"Status: {status}")

        progress_pct = result.get("progress_pct")
        if isinstance(progress_pct, (int, float)):
            lines.append(f"Progress: {round(float(progress_pct), 2)}%")

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
            lines.append("\nIngestion Timeline:")
            for index, step in enumerate(steps, start=1):
                if not isinstance(step, dict):
                    continue
                ordinal = step.get("ordinal")
                display_index = int(ordinal) if isinstance(ordinal, int) else index
                name = str(step.get("name", "step"))
                step_status = str(step.get("status", "ok"))
                elapsed_ms = step.get("elapsed_ms")
                elapsed_hint = ""
                if isinstance(elapsed_ms, (int, float)):
                    elapsed_hint = f" ({round(float(elapsed_ms), 2)} ms)"
                lines.append(
                    f"{display_index}. [{step_status}] {name}{elapsed_hint}"
                )
                details = step.get("details", {})
                if isinstance(details, dict):
                    for key, value in details.items():
                        if key == "progress_pct":
                            continue
                        lines.append(f"   - {key}: {value}")

            durations = [
                float(step.get("elapsed_ms"))
                for step in steps
                if isinstance(step, dict)
                and isinstance(step.get("elapsed_ms"), (int, float))
            ]
            if durations:
                lines.append("\nProgress Summary:")
                lines.append(f"- total_elapsed_ms: {round(max(durations), 2)}")
                lines.append(f"- recorded_steps: {len(durations)}")

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
