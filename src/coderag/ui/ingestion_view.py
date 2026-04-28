"""Ingestion panel for source configuration and indexing."""

from __future__ import annotations

import json
from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt
from PySide6.QtGui import QKeySequence, QRegularExpressionValidator, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QCheckBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QRegularExpression


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
        on_delete_document: Callable[[str], dict] | None = None,
        on_ingestion_readiness: Callable[[], dict] | None = None,
    ) -> None:
        super().__init__()
        self._on_ingest = on_ingest
        self._on_reset_all = on_reset_all
        self._on_delete_document = on_delete_document
        self._on_ingestion_readiness = on_ingestion_readiness
        self._ingest_thread: QThread | None = None
        self._ingest_worker: _IngestionWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        form_group = QGroupBox("Configuracion de fuente")
        form_layout = QFormLayout(form_group)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(10)

        self.source_type = QLineEdit("folder")
        self.source_type.setMinimumHeight(34)
        self.ingestion_channel = QComboBox()
        self.ingestion_channel.setMinimumHeight(34)
        self.ingestion_channel.addItem(
            "Carpeta (JSON)",
            "json_folder",
        )
        self.ingestion_channel.addItem(
            "Archivo (multipart upload)",
            "upload_file",
        )
        self.ingestion_channel.setCurrentIndex(0)
        self.execution_mode = QComboBox()
        self.execution_mode.setMinimumHeight(34)
        self.execution_mode.addItem("Asincrono (cola + jobs)", "async")
        self.execution_mode.addItem("Sincrono (directo)", "sync")
        self.execution_mode.setCurrentIndex(0)
        self.local_path = QLineEdit("sample_data")
        self.local_path.setMinimumHeight(34)
        self.local_path.setClearButtonEnabled(True)
        self.base_url = QLineEdit()
        self.base_url.setMinimumHeight(34)
        self.base_url.setClearButtonEnabled(True)
        self.token = QLineEdit()
        self.token.setMinimumHeight(34)
        self.filters = QLineEdit("{}")
        self.filters.setMinimumHeight(34)

        self.source_type.setPlaceholderText("folder | confluence")
        self.source_type.setToolTip(
            "Use 'folder' para archivos locales o 'confluence' para ingesta API."
        )
        self.ingestion_channel.setToolTip(
            "Selecciona JSON tradicional por carpeta o upload multipart para "
            "probar el endpoint /sources/ingest/file*."
        )
        self.execution_mode.setToolTip(
            "Asincrono requiere cola operativa; Sincrono ejecuta ingesta en "
            "la llamada HTTP sin polling de jobs."
        )
        self.local_path.setPlaceholderText("sample_data o C:/ruta/a/documentos")
        self.local_path.setToolTip("Obligatorio para ingesta de tipo folder.")
        self.base_url.setPlaceholderText("https://company.atlassian.net/wiki")
        self.base_url.setToolTip("Obligatorio para ingesta de tipo confluence.")
        self.token.setPlaceholderText("Token API de Confluence")
        self.token.setToolTip("Dato sensible. Usa mostrar/ocultar segun tu entorno.")
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.filters.setPlaceholderText('{"space": "ENG", "labels": ["policy"]}')
        self.filters.setToolTip("Objeto JSON opcional para filtros del origen.")

        source_pattern = QRegularExpression("^[a-zA-Z_][a-zA-Z0-9_-]*$")
        self.source_type.setValidator(QRegularExpressionValidator(source_pattern))

        form_layout.addRow("Tipo de fuente", self.source_type)
        form_layout.addRow("Canal de envio", self.ingestion_channel)
        form_layout.addRow("Modo de ejecucion", self.execution_mode)
        form_layout.addRow("Ruta local", self.local_path)
        form_layout.addRow("URL base", self.base_url)
        form_layout.addRow("Token", self.token)
        form_layout.addRow("Filtros (JSON)", self.filters)

        actions = QHBoxLayout()
        self.ingest_button = QPushButton("Ingerir")
        self.ingest_button.setProperty("variant", "primary")
        self.ingest_button.clicked.connect(self._run_ingestion)
        self.reset_all_button = QPushButton("BORRAR TODO")
        self.reset_all_button.setProperty("variant", "danger")
        self.reset_all_button.clicked.connect(self._run_reset_all)
        actions.addWidget(self.ingest_button)
        actions.addWidget(self.reset_all_button)

        self.status_badge = QLabel("idle")
        self.status_badge.setProperty("role", "status")
        self.status_badge.setProperty("state", "idle")
        actions.addWidget(self.status_badge)

        self.summary_label = QLabel("Listo para ingerir")
        self.summary_label.setProperty("role", "hint")
        actions.addStretch(1)
        actions.addWidget(self.summary_label)

        delete_group = QGroupBox("Borrado puntual")
        delete_layout = QFormLayout(delete_group)
        delete_layout.setHorizontalSpacing(12)
        delete_layout.setVerticalSpacing(10)

        self.delete_document_id = QLineEdit()
        self.delete_document_id.setMinimumHeight(34)
        self.delete_document_id.setClearButtonEnabled(True)
        self.delete_document_id.setPlaceholderText("document_id a eliminar")
        self.delete_document_id.setToolTip(
            "Elimina un documento puntual ya persistido usando su document_id."
        )

        self.delete_document_button = QPushButton("Eliminar documento")
        self.delete_document_button.setProperty("variant", "danger")
        self.delete_document_button.clicked.connect(self._run_delete_document)

        delete_row = QWidget()
        delete_row_layout = QHBoxLayout(delete_row)
        delete_row_layout.setContentsMargins(0, 0, 0, 0)
        delete_row_layout.setSpacing(8)
        delete_row_layout.addWidget(self.delete_document_id)
        delete_row_layout.addWidget(self.delete_document_button)
        delete_layout.addRow("Document ID", delete_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setFixedHeight(110)

        self.show_raw = QCheckBox("Mostrar timeline tecnico y JSON crudo")
        self.show_raw.setChecked(True)
        self.show_raw.toggled.connect(self._toggle_raw_output)

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        layout.addWidget(form_group)
        layout.addLayout(actions)
        layout.addWidget(delete_group)
        layout.addWidget(self.progress)
        layout.addWidget(self.show_raw)

        self.feedback_splitter = QSplitter(Qt.Orientation.Vertical)
        self.feedback_splitter.addWidget(self.summary)
        self.feedback_splitter.addWidget(self.output)
        self.feedback_splitter.setChildrenCollapsible(False)
        self.feedback_splitter.setStretchFactor(0, 1)
        self.feedback_splitter.setStretchFactor(1, 2)
        self.feedback_splitter.setSizes([170, 330])
        layout.addWidget(self.feedback_splitter)

        self._ingest_shortcut = QShortcut(QKeySequence("Ctrl+I"), self)
        self._ingest_shortcut.activated.connect(self._run_ingestion)
        self._toggle_raw_shortcut = QShortcut(QKeySequence("Ctrl+T"), self)
        self._toggle_raw_shortcut.activated.connect(self.show_raw.toggle)

        QWidget.setTabOrder(self.source_type, self.ingestion_channel)
        QWidget.setTabOrder(self.ingestion_channel, self.execution_mode)
        QWidget.setTabOrder(self.execution_mode, self.local_path)
        QWidget.setTabOrder(self.local_path, self.base_url)
        QWidget.setTabOrder(self.base_url, self.token)
        QWidget.setTabOrder(self.token, self.filters)
        QWidget.setTabOrder(self.filters, self.delete_document_id)
        QWidget.setTabOrder(self.delete_document_id, self.delete_document_button)
        QWidget.setTabOrder(self.delete_document_button, self.ingest_button)
        QWidget.setTabOrder(self.ingest_button, self.reset_all_button)

        self.delete_document_id.textChanged.connect(
            self._refresh_delete_document_state
        )

        self._set_status("idle")
        self._refresh_delete_document_state()
        self.summary.setPlainText(
            "Estado: inactivo\nEsperando configuracion de fuente."
        )

    def _run_ingestion(self) -> None:
        if self._ingest_thread is not None and self._ingest_thread.isRunning():
            self.summary.setPlainText(
                "Estado: en curso\nYa existe una ingesta en ejecucion."
            )
            return

        validation_error = self._validate_inputs()
        if validation_error:
            self._set_status("error")
            self.summary.setPlainText(
                "Estado: failed\n"
                f"{validation_error}\n"
                "Accion sugerida: corrige el formulario y vuelve a intentar."
            )
            return

        payload = {
            "source": {
                "source_type": self.source_type.text().strip() or "folder",
                "local_path": self.local_path.text().strip() or None,
                "base_url": self.base_url.text().strip() or None,
                "token": self.token.text().strip() or None,
                "filters": self._safe_json(self.filters.text().strip()),
            },
            "_ingestion_channel": str(
                self.ingestion_channel.currentData() or "json_folder"
            ),
            "_ingestion_mode": str(self.execution_mode.currentData() or "async"),
        }

        execution_mode = str(payload.get("_ingestion_mode") or "async")
        if execution_mode == "async" and self._on_ingestion_readiness is not None:
            readiness = self._on_ingestion_readiness()
            if not self._is_async_ready(readiness):
                self.execution_mode.setCurrentIndex(1)
                payload["_ingestion_mode"] = "sync"
                self.summary.setPlainText(
                    "Estado: en curso\n"
                    "Dependencias async no listas; se ejecutara en modo sincrono."
                )
                self.output.setPlainText(self._format_async_readiness(readiness))
        selected_mode = str(payload.get("_ingestion_mode") or "async")
        channel = str(payload.get("_ingestion_channel") or "json_folder")
        dispatch_message = "Enviando job de ingesta..."
        if selected_mode == "sync":
            dispatch_message = "Ejecutando ingesta sincrona..."
        if channel == "upload_file":
            dispatch_message = "Subiendo archivo para ingesta..."
            if selected_mode == "sync":
                dispatch_message = "Subiendo archivo y ejecutando ingesta sincrona..."
        self.summary.setPlainText(
            f"Estado: en curso\n{dispatch_message}"
        )
        self.progress.setValue(0)
        self._set_status("running")
        self.ingest_button.setEnabled(False)
        self.reset_all_button.setEnabled(False)
        self.delete_document_button.setEnabled(False)

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
        self._update_progress(result)
        self._render_summary(result)
        rendered = self._format_ingestion_result(result, include_raw=True)
        self.output.setPlainText(rendered)
        QApplication.processEvents()

    @Slot(dict)
    def _handle_ingestion_finished(self, result: dict) -> None:
        """Render final ingestion result and restore UI state."""
        self._update_progress(result)
        self._render_summary(result)
        rendered = self._format_ingestion_result(result, include_raw=True)
        self.output.setPlainText(rendered)
        final_state = self._status_to_badge(result.get("status"))
        self._set_status(final_state)
        self.ingest_button.setEnabled(True)
        self.reset_all_button.setEnabled(True)
        self._refresh_delete_document_state()

    @Slot(str)
    def _handle_ingestion_failed(self, error: str) -> None:
        """Render unexpected worker errors and restore UI state."""
        self._set_status("error")
        self.summary.setPlainText(
            "Estado: failed\n"
            f"Error inesperado en worker UI: {error}\n"
            "Accion sugerida: revisar conectividad de API y logs del backend."
        )
        self.output.setPlainText(
            "Status: failed\n"
            f"Message: Unexpected ingestion error in UI worker: {error}"
        )
        self.ingest_button.setEnabled(True)
        self.reset_all_button.setEnabled(True)
        self._refresh_delete_document_state()

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
                "ChromaDB embebido, staging espejo local, Neo4j y jobs "
                "historicos.\n\n"
                "Deseas continuar?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if decision != QMessageBox.StandardButton.Yes:
            self._set_status("idle")
            self.summary.setPlainText(
                "Estado: inactivo\nReset cancelado por el usuario."
            )
            return

        self._set_status("running")
        self.summary.setPlainText("Estado: en curso\nReset en ejecucion...")
        self.progress.setValue(0)
        QApplication.processEvents()
        result = self._on_reset_all()
        self._update_progress(result)
        self._render_summary(result)
        rendered = self._format_ingestion_result(result, include_raw=True)
        self.output.setPlainText(rendered)
        self._set_status(self._status_to_badge(result.get("status")))

    def _run_delete_document(self) -> None:
        """Run one-document deletion after explicit user confirmation."""
        if self._on_delete_document is None:
            self._set_status("error")
            self.summary.setPlainText(
                "Estado: fallido\n"
                "El backend configurado no expone borrado puntual de documentos."
            )
            return

        document_id = (self.delete_document_id.text() or "").strip()
        if not document_id:
            self._set_status("error")
            self.summary.setPlainText(
                "Estado: fallido\n"
                "Debes indicar un document_id antes de eliminar."
            )
            self._refresh_delete_document_state()
            return

        decision = QMessageBox.question(
            self,
            "Confirmar borrado puntual",
            (
                "Esta accion eliminara de forma persistente el documento "
                f"'{document_id}'.\n\n"
                "Se borraran metadatos, chunks, vectores y mirror de staging "
                "cuando aplique."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if decision != QMessageBox.StandardButton.Yes:
            self._set_status("idle")
            self.summary.setPlainText(
                "Estado: inactivo\nBorrado puntual cancelado por el usuario."
            )
            return

        self._set_status("running")
        self.summary.setPlainText(
            f"Estado: en curso\nEliminando document_id: {document_id}"
        )
        self.progress.setValue(0)
        QApplication.processEvents()

        result = self._on_delete_document(document_id)
        self._render_delete_document_result(result, document_id)

    def _render_delete_document_result(
        self,
        result: dict,
        requested_document_id: str,
    ) -> None:
        """Render operator-facing status for one-document delete actions."""
        self._update_progress(result)
        status = str(result.get("status") or "failed").strip().lower()
        if status in {"completed", "finished"}:
            self.progress.setValue(100)

        message = str(result.get("message") or result.get("detail") or "")
        source_id = str(result.get("source_id") or "-")
        deleted_documents = result.get("deleted_documents", 0)
        deleted_chunks = result.get("deleted_chunks", 0)
        deleted_staging = result.get("deleted_staging_files", 0)
        reindexed_sources = result.get("reindexed_sources", 0)

        self.summary.setPlainText(
            "\n".join(
                [
                    f"Estado: {self._localize_status(status)}",
                    f"Mensaje: {message or 'Sin mensaje'}",
                    f"Document ID: {requested_document_id}",
                    f"Source ID: {source_id}",
                    f"Documentos eliminados: {deleted_documents}",
                    f"Chunks eliminados: {deleted_chunks}",
                    f"Staging eliminado: {deleted_staging}",
                    f"Sources resincronizados: {reindexed_sources}",
                ]
            )
        )
        self.output.setPlainText(
            self._format_ingestion_result(result, include_raw=True)
        )
        self._set_status(self._status_to_badge(status))
        if status in {"completed", "finished"}:
            self.delete_document_id.clear()
        self._refresh_delete_document_state()

    def _refresh_delete_document_state(self) -> None:
        """Keep one-document delete action enabled only when usable."""
        can_delete = self._on_delete_document is not None
        has_document_id = bool((self.delete_document_id.text() or "").strip())
        is_ingesting = bool(
            self._ingest_thread is not None and self._ingest_thread.isRunning()
        )
        self.delete_document_button.setEnabled(
            can_delete and has_document_id and not is_ingesting
        )

    @staticmethod
    def _format_deduplication_paths(
        deduplication: dict,
        limit: int = 2,
    ) -> str:
        """Build a short UI summary for discarded and replaced document paths."""
        incoming = deduplication.get("incoming_batch", {})
        replaced = deduplication.get("replaced_existing", {})
        if not isinstance(incoming, dict) or not isinstance(replaced, dict):
            return "-"

        skipped_paths = incoming.get("kept_paths", [])
        replaced_paths = replaced.get("replaced_paths", [])

        fragments: list[str] = []
        if isinstance(skipped_paths, list) and skipped_paths:
            shown = ", ".join(str(path) for path in skipped_paths[:limit])
            extra = max(0, len(skipped_paths) - limit)
            suffix = f" (+{extra})" if extra else ""
            fragments.append(f"conservados: {shown}{suffix}")

        if isinstance(replaced_paths, list) and replaced_paths:
            shown = ", ".join(str(path) for path in replaced_paths[:limit])
            extra = max(0, len(replaced_paths) - limit)
            suffix = f" (+{extra})" if extra else ""
            fragments.append(f"reemplazados: {shown}{suffix}")

        return " | ".join(fragments) if fragments else "-"

    @staticmethod
    def _format_ingestion_result(result: dict, include_raw: bool) -> str:
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

        deduplication = result.get("deduplication")
        if isinstance(deduplication, dict) and deduplication:
            lines.append("\nDeduplication:")
            for section_name, section in deduplication.items():
                if not isinstance(section, dict):
                    continue
                lines.append(f"- {section_name}:")
                for key, value in section.items():
                    lines.append(f"  - {key}: {value}")

        steps = result.get("steps")
        if isinstance(steps, list) and steps:
            lines.append("\nIngestion Timeline:")
            timed_steps = 0
            total_elapsed = ""
            for index, step in enumerate(steps, start=1):
                if not isinstance(step, dict):
                    continue
                ordinal = step.get("ordinal")
                display_index = int(ordinal) if isinstance(ordinal, int) else index
                name = str(step.get("name", "step"))
                step_status = str(step.get("status", "ok"))
                elapsed_hhmmss = step.get("elapsed_hhmmss")
                elapsed_hint = ""
                if isinstance(elapsed_hhmmss, str) and elapsed_hhmmss:
                    elapsed_hint = f" ({elapsed_hhmmss})"
                    timed_steps += 1
                    total_elapsed = elapsed_hhmmss
                lines.append(
                    f"{display_index}. [{step_status}] {name}{elapsed_hint}"
                )
                details = step.get("details", {})
                if isinstance(details, dict):
                    for key, value in details.items():
                        if key == "progress_pct":
                            continue
                        lines.append(f"   - {key}: {value}")

            if timed_steps > 0:
                lines.append("\nProgress Summary:")
                lines.append(f"- total_elapsed_hhmmss: {total_elapsed}")
                lines.append(f"- recorded_steps: {timed_steps}")

        if include_raw:
            lines.append("\nRaw JSON:")
            lines.append(json.dumps(result, indent=2, ensure_ascii=False))
        return "\n".join(lines)

    def _toggle_raw_output(self, checked: bool) -> None:
        """Toggle technical output visibility without touching summary panel."""
        self.output.setVisible(checked)

    def _update_progress(self, result: dict) -> None:
        """Update progress bar from backend progress percentage."""
        progress_pct = result.get("progress_pct")
        if isinstance(progress_pct, (int, float)):
            bounded = max(0, min(100, int(round(float(progress_pct)))))
            self.progress.setValue(bounded)
            return
        status = str(result.get("status", "")).strip().lower()
        if status in {"completed", "finished"}:
            self.progress.setValue(100)
        elif status == "failed":
            self.progress.setValue(0)

    def _render_summary(self, result: dict) -> None:
        """Render concise status summary separate from technical timeline."""
        raw_status = str(result.get("status", "unknown"))
        status = self._localize_status(raw_status)
        message = str(result.get("message", "")).strip() or "No message provided."
        documents = result.get("documents", "-")
        chunks = result.get("chunks", "-")
        elapsed = "-"
        dedup_summary = "-"
        dedup_paths = "-"

        deduplication = result.get("deduplication")
        if isinstance(deduplication, dict):
            incoming = deduplication.get("incoming_batch", {})
            replaced = deduplication.get("replaced_existing", {})
            if isinstance(incoming, dict) and isinstance(replaced, dict):
                incoming_skipped = incoming.get("skipped_documents", 0)
                replaced_deleted = replaced.get("deleted_documents", 0)
                dedup_summary = (
                    f"lote={incoming_skipped} | reemplazos={replaced_deleted}"
                )
            dedup_paths = self._format_deduplication_paths(deduplication)

        steps = result.get("steps")
        if isinstance(steps, list) and steps:
            for step in reversed(steps):
                if not isinstance(step, dict):
                    continue
                elapsed_candidate = step.get("elapsed_hhmmss")
                if isinstance(elapsed_candidate, str) and elapsed_candidate:
                    elapsed = elapsed_candidate
                    break

        self.summary.setPlainText(
            "\n".join(
                [
                    f"Estado: {status}",
                    f"Mensaje: {message}",
                    f"Documentos: {documents}",
                    f"Chunks: {chunks}",
                    f"Deduplicacion: {dedup_summary}",
                    f"Detalle deduplicacion: {dedup_paths}",
                    f"Duracion: {elapsed}",
                ]
            )
        )

    def _set_status(self, state: str) -> None:
        """Apply status style token for ingestion lifecycle."""
        label_by_state = {
            "idle": "inactivo",
            "running": "en curso",
            "success": "ok",
            "error": "error",
        }
        self.status_badge.setProperty("state", state)
        self.status_badge.setText(label_by_state.get(state, "inactivo"))
        hints = {
            "idle": "Listo para ingerir",
            "running": "Procesando fuente",
            "success": "Ingesta completada",
            "error": "Revisar validacion o errores de backend",
        }
        self.summary_label.setText(hints.get(state, "Ready"))
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)
        self.status_badge.update()

    @staticmethod
    def _is_async_ready(payload: dict) -> bool:
        """Return True when async ingestion dependencies are reported ready."""
        ready = payload.get("ready")
        if isinstance(ready, bool):
            return ready
        return False

    @staticmethod
    def _format_async_readiness(payload: dict) -> str:
        """Format readiness payload for operator-facing technical output."""
        checks = payload.get("checks") if isinstance(payload, dict) else None
        lines = ["Readiness de ingesta asincrona:"]
        lines.append(f"- ready: {payload.get('ready')}")
        lines.append(
            f"- recommendation: {payload.get('recommendation', 'sync')}"
        )
        if isinstance(checks, dict):
            for name, value in checks.items():
                if not isinstance(value, dict):
                    continue
                lines.append(
                    "- "
                    f"{name}: ok={value.get('ok')} "
                    f"required={value.get('required')} "
                    f"detail={value.get('detail', '')}"
                )
        return "\n".join(lines)

    @staticmethod
    def _localize_status(status: str) -> str:
        """Map backend status values to UI-friendly Spanish labels."""
        normalized = status.strip().lower()
        mapping = {
            "queued": "en cola",
            "running": "en curso",
            "started": "en curso",
            "completed": "completado",
            "finished": "completado",
            "failed": "fallido",
            "idle": "inactivo",
        }
        return mapping.get(normalized, normalized or "desconocido")

    @staticmethod
    def _status_to_badge(status: object) -> str:
        """Map backend status string to known badge tokens."""
        normalized = str(status or "").strip().lower()
        if normalized in {"completed", "finished"}:
            return "success"
        if normalized == "failed":
            return "error"
        if normalized in {"queued", "running", "started"}:
            return "running"
        return "idle"

    def _validate_inputs(self) -> str | None:
        """Validate source-specific fields before dispatching ingestion."""
        source_type = (self.source_type.text() or "").strip().lower()
        ingestion_channel = str(
            self.ingestion_channel.currentData() or "json_folder"
        )
        filters_raw = (self.filters.text() or "").strip()

        if not source_type:
            self.source_type.setProperty("invalid", True)
            self._refresh_input_style(self.source_type)
            return "El tipo de fuente es obligatorio."

        self.source_type.setProperty("invalid", False)
        self._refresh_input_style(self.source_type)

        if source_type == "folder":
            if not (self.local_path.text() or "").strip():
                self.local_path.setProperty("invalid", True)
                self._refresh_input_style(self.local_path)
                return "La ruta local es obligatoria cuando el tipo es folder."
            self.local_path.setProperty("invalid", False)
            self._refresh_input_style(self.local_path)

        if ingestion_channel == "upload_file" and source_type != "folder":
            return (
                "El canal de upload por archivo requiere tipo de fuente "
                "'folder'."
            )

        if source_type == "confluence":
            has_base_url = bool((self.base_url.text() or "").strip())
            has_token = bool((self.token.text() or "").strip())
            self.base_url.setProperty("invalid", not has_base_url)
            self.token.setProperty("invalid", not has_token)
            self._refresh_input_style(self.base_url)
            self._refresh_input_style(self.token)
            if not has_base_url or not has_token:
                return "URL base y token son obligatorios para fuentes confluence."

        self.base_url.setProperty("invalid", False)
        self.token.setProperty("invalid", False)
        self._refresh_input_style(self.base_url)
        self._refresh_input_style(self.token)

        if filters_raw:
            parsed = self._safe_json(filters_raw)
            is_invalid_json = parsed == {} and filters_raw not in {"{}", ""}
            self.filters.setProperty("invalid", is_invalid_json)
            self._refresh_input_style(self.filters)
            if is_invalid_json:
                return "Los filtros deben ser un objeto JSON valido."

        self.filters.setProperty("invalid", False)
        self._refresh_input_style(self.filters)
        return None

    @staticmethod
    def _refresh_input_style(widget: QLineEdit) -> None:
        """Re-apply stylesheet when dynamic input state changes."""
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

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
