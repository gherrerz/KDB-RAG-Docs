"""Query panel for asking grounded questions."""

from __future__ import annotations

import json
from typing import Any, Callable, Sequence

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QIntValidator, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from coderag.ui.evidence_view import EvidenceView


class DocumentPickerDialog(QDialog):
    """Modal multi-select dialog for ingested document catalog entries."""

    def __init__(
        self,
        documents: Sequence[dict[str, Any]],
        selected_ids: Sequence[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Seleccionar documentos")
        self.resize(760, 520)

        selected_lookup = {item for item in selected_ids if item}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.summary_label = QLabel(
            f"{len(documents)} documentos disponibles para seleccionar"
        )
        self.summary_label.setProperty("role", "hint")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText(
            "Filtrar por titulo, path o source_id"
        )
        self.filter_input.setClearButtonEnabled(True)
        layout.addWidget(self.filter_input)

        self.empty_state_label = QLabel(
            "Sin coincidencias para el filtro actual."
        )
        self.empty_state_label.setProperty("role", "hint")
        self.empty_state_label.setVisible(False)
        layout.addWidget(self.empty_state_label)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )
        layout.addWidget(self.list_widget)

        button_row = QHBoxLayout()
        self.select_all_button = QPushButton("Seleccionar todo")
        self.select_all_button.clicked.connect(self._select_visible)
        self.clear_selection_button = QPushButton("Limpiar seleccion")
        self.clear_selection_button.clicked.connect(self.list_widget.clearSelection)
        self.clear_selection_button.setProperty("variant", "danger")
        self.count_label = QLabel("0 seleccionados")
        self.count_label.setProperty("role", "hint")
        button_row.addWidget(self.select_all_button)
        button_row.addWidget(self.clear_selection_button)
        button_row.addWidget(self.count_label)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setProperty("variant", "primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        for document in documents:
            item = QListWidgetItem(self._render_label(document))
            item.setData(Qt.ItemDataRole.UserRole, document)
            item.setSelected(
                str(document.get("document_id") or "") in selected_lookup
            )
            self.list_widget.addItem(item)

        self.filter_input.textChanged.connect(self._apply_filter)
        self.list_widget.itemSelectionChanged.connect(self._update_count_label)
        self._apply_filter("")
        self._update_count_label()

    @staticmethod
    def _render_label(document: dict[str, Any]) -> str:
        """Build a readable item label for document picker rows."""
        title = str(document.get("title") or document.get("document_id") or "")
        path_or_url = str(document.get("path_or_url") or "").strip()
        source_id = str(document.get("source_id") or "").strip()
        suffix = []
        if source_id:
            suffix.append(source_id)
        if path_or_url:
            suffix.append(path_or_url.replace("\\", "/"))
        if suffix:
            return f"{title} | {' | '.join(suffix)}"
        return title

    def _apply_filter(self, raw_text: str) -> None:
        """Hide rows that do not match the current free-text filter."""
        needle = raw_text.casefold().strip()
        visible_count = 0
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            payload = item.data(Qt.ItemDataRole.UserRole) or {}
            haystack = " ".join(
                [
                    str(payload.get("title") or ""),
                    str(payload.get("path_or_url") or ""),
                    str(payload.get("source_id") or ""),
                ]
            ).casefold()
            is_hidden = bool(needle) and needle not in haystack
            item.setHidden(is_hidden)
            if not is_hidden:
                visible_count += 1
        self.empty_state_label.setVisible(visible_count == 0)
        self.select_all_button.setEnabled(visible_count > 0)

    def _select_visible(self) -> None:
        """Select all currently visible rows."""
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if not item.isHidden():
                item.setSelected(True)
        self._update_count_label()

    def _update_count_label(self) -> None:
        """Refresh helper text with the number of selected documents."""
        self.count_label.setText(
            f"{len(self.selected_documents())} seleccionados"
        )

    def selected_documents(self) -> list[dict[str, Any]]:
        """Return selected document payloads in visible order."""
        selected: list[dict[str, Any]] = []
        for item in self.list_widget.selectedItems():
            payload = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(payload, dict):
                selected.append(payload)
        return selected


class QueryView(QWidget):
    """Widget for querying backend and presenting evidence."""

    def __init__(
        self,
        on_query: Callable[[dict], dict],
        on_list_documents: Callable[[str | None], dict] | None = None,
        on_delete_document: Callable[[str], dict] | None = None,
    ) -> None:
        super().__init__()
        self._on_query = on_query
        self._on_list_documents = on_list_documents
        self._on_delete_document = on_delete_document
        self._selected_documents: list[dict[str, Any]] = []
        self._available_documents: list[dict[str, Any]] = []

        self._document_refresh_timer = QTimer(self)
        self._document_refresh_timer.setSingleShot(True)
        self._document_refresh_timer.setInterval(250)
        self._document_refresh_timer.timeout.connect(
            self._refresh_document_catalog_silent
        )

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        group = QGroupBox("Consulta")
        form = QFormLayout(group)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        self.question = QLineEdit()
        self.question.setMinimumHeight(34)
        self.question.setClearButtonEnabled(True)
        self.source_id = QLineEdit()
        self.source_id.setMinimumHeight(34)
        self.source_id.setClearButtonEnabled(True)
        self.source_id.textChanged.connect(self._handle_source_id_change)
        self.document_picker_button = QPushButton("Seleccionar documentos")
        self.document_picker_button.setMinimumHeight(34)
        self.document_picker_button.clicked.connect(self._open_document_picker)
        self.document_refresh_button = QPushButton("Actualizar")
        self.document_refresh_button.setMinimumHeight(34)
        self.document_refresh_button.clicked.connect(
            lambda: self._refresh_document_catalog(show_feedback=True)
        )
        self.delete_documents_button = QPushButton("Eliminar seleccionados")
        self.delete_documents_button.setMinimumHeight(34)
        self.delete_documents_button.setProperty("variant", "danger")
        self.delete_documents_button.clicked.connect(
            self._delete_selected_documents
        )
        self.clear_documents_button = QPushButton("Limpiar")
        self.clear_documents_button.setMinimumHeight(34)
        self.clear_documents_button.clicked.connect(self._clear_selected_documents)
        self.selected_documents_label = QLabel("Sin filtro por documento")
        self.selected_documents_label.setProperty("role", "hint")
        self.selected_documents_label.setWordWrap(True)
        self.document_catalog_label = QLabel("Catalogo sin cargar")
        self.document_catalog_label.setProperty("role", "status")
        self.document_catalog_label.setProperty("state", "idle")
        self.hops = QLineEdit("2")
        self.hops.setMinimumHeight(34)
        self.hops.setValidator(QIntValidator(1, 6, self))
        self.include_llm_answer = QCheckBox("Incluir respuesta LLM")
        self.include_llm_answer.setChecked(True)
        self.include_llm_answer.toggled.connect(self._sync_response_mode)

        self.response_mode_badge = QLabel("")
        self.response_mode_badge.setProperty("role", "status")

        self.question.setPlaceholderText("Formula una pregunta basada en tus documentos")
        self.question.setToolTip("Presiona Ctrl+Enter para ejecutar rapidamente.")
        self.source_id.setPlaceholderText("source_id opcional para acotar busqueda")
        self.source_id.setToolTip(
            "Dejalo vacio para consultar sobre todas las fuentes indexadas."
        )
        self.document_picker_button.setToolTip(
            "Selecciona uno o mas documentos ingestados para acotar la consulta."
        )
        self.document_refresh_button.setToolTip(
            "Recarga el catalogo de documentos desde la API activa."
        )
        self.delete_documents_button.setToolTip(
            "Elimina de forma persistente los documentos seleccionados en el filtro actual."
        )
        self.hops.setPlaceholderText("1-6")
        self.hops.setToolTip(
            "Profundidad de expansion del grafo. Recomendado: 2."
        )

        form.addRow("Pregunta", self.question)
        form.addRow("Source ID (opcional)", self.source_id)
        document_row = QWidget()
        document_row_layout = QHBoxLayout(document_row)
        document_row_layout.setContentsMargins(0, 0, 0, 0)
        document_row_layout.setSpacing(8)
        document_row_layout.addWidget(self.document_picker_button)
        document_row_layout.addWidget(self.document_refresh_button)
        document_row_layout.addWidget(self.delete_documents_button)
        document_row_layout.addWidget(self.clear_documents_button)
        document_row_layout.addWidget(self.selected_documents_label, 1)
        document_row_layout.addWidget(self.document_catalog_label)
        form.addRow("Documentos (opcional)", document_row)
        form.addRow("Saltos de grafo", self.hops)
        response_mode_row = QWidget()
        response_mode_layout = QHBoxLayout(response_mode_row)
        response_mode_layout.setContentsMargins(0, 0, 0, 0)
        response_mode_layout.setSpacing(10)
        response_mode_layout.addWidget(self.include_llm_answer)
        response_mode_layout.addWidget(self.response_mode_badge)
        response_mode_layout.addStretch(1)
        form.addRow("Modo de respuesta", response_mode_row)

        actions = QHBoxLayout()
        self.query_button = QPushButton("Consultar")
        self.query_button.setProperty("variant", "primary")
        self.query_button.clicked.connect(self._run_query)
        actions.addWidget(self.query_button)
        self.status_label = QLabel("Listo")
        self.status_label.setProperty("role", "status")
        self.status_label.setProperty("state", "idle")
        actions.addWidget(self.status_label)
        self.status_message = QLabel("Listo para consultar")
        self.status_message.setProperty("role", "hint")
        actions.addWidget(self.status_message)
        self.hint_label = QLabel("Recuperacion hibrida + expansion de grafo")
        self.hint_label.setProperty("role", "hint")
        actions.addStretch(1)
        actions.addWidget(self.hint_label)

        self.answer_title = QLabel("Respuesta")
        self.answer = QTextEdit()
        self.answer.setReadOnly(True)

        self.diagnostics = QTextEdit()
        self.diagnostics.setReadOnly(True)
        self.diagnostics.setFixedHeight(120)
        self.show_diagnostics = QCheckBox("Mostrar diagnosticos")
        self.show_diagnostics.setChecked(True)
        self.show_diagnostics.toggled.connect(self._toggle_diagnostics)

        self.raw_label = QLabel("JSON crudo (tecnico)")
        self.raw_response = QTextEdit()
        self.raw_response.setReadOnly(True)
        self.raw_response.setFixedHeight(140)
        self.show_raw = QCheckBox("Mostrar JSON crudo")
        self.show_raw.setChecked(True)
        self.show_raw.toggled.connect(self._toggle_raw)

        self.evidence = EvidenceView()

        layout.addWidget(group)
        layout.addLayout(actions)

        answer_panel = QWidget()
        answer_layout = QVBoxLayout(answer_panel)
        answer_layout.setContentsMargins(0, 0, 0, 0)
        answer_layout.setSpacing(6)
        answer_layout.addWidget(self.answer_title)
        answer_layout.addWidget(self.answer)

        diagnostics_panel = QWidget()
        diagnostics_layout = QVBoxLayout(diagnostics_panel)
        diagnostics_layout.setContentsMargins(0, 0, 0, 0)
        diagnostics_layout.setSpacing(6)
        self.diagnostics_label = QLabel("Diagnosticos")
        diagnostics_layout.addWidget(self.show_diagnostics)
        diagnostics_layout.addWidget(self.diagnostics_label)
        diagnostics_layout.addWidget(self.diagnostics)

        raw_panel = QWidget()
        raw_layout = QVBoxLayout(raw_panel)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        raw_layout.setSpacing(6)
        raw_layout.addWidget(self.show_raw)
        raw_layout.addWidget(self.raw_label)
        raw_layout.addWidget(self.raw_response)

        self.content_splitter = QSplitter(Qt.Orientation.Vertical)
        self.content_splitter.addWidget(answer_panel)
        self.content_splitter.addWidget(diagnostics_panel)
        self.content_splitter.addWidget(raw_panel)
        self.content_splitter.addWidget(self.evidence)
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.setStretchFactor(0, 2)
        self.content_splitter.setStretchFactor(1, 1)
        self.content_splitter.setStretchFactor(2, 1)
        self.content_splitter.setStretchFactor(3, 3)
        self.content_splitter.setSizes([220, 170, 170, 340])
        self.content_splitter.setMinimumHeight(760)
        layout.addWidget(self.content_splitter)

        scroll.setWidget(content)
        root_layout.addWidget(scroll)

        self._query_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self._query_shortcut.activated.connect(self._run_query)
        self._query_shortcut_2 = QShortcut(QKeySequence("Ctrl+Enter"), self)
        self._query_shortcut_2.activated.connect(self._run_query)
        self._toggle_diag_shortcut = QShortcut(QKeySequence("Ctrl+D"), self)
        self._toggle_diag_shortcut.activated.connect(self.show_diagnostics.toggle)
        self._toggle_raw_shortcut = QShortcut(QKeySequence("Ctrl+J"), self)
        self._toggle_raw_shortcut.activated.connect(self.show_raw.toggle)
        self.question.returnPressed.connect(self._run_query)

        QWidget.setTabOrder(self.question, self.source_id)
        QWidget.setTabOrder(self.source_id, self.document_picker_button)
        QWidget.setTabOrder(self.document_picker_button, self.document_refresh_button)
        QWidget.setTabOrder(self.document_refresh_button, self.delete_documents_button)
        QWidget.setTabOrder(self.delete_documents_button, self.clear_documents_button)
        QWidget.setTabOrder(self.clear_documents_button, self.hops)
        QWidget.setTabOrder(self.hops, self.include_llm_answer)
        QWidget.setTabOrder(self.include_llm_answer, self.query_button)
        QWidget.setTabOrder(self.query_button, self.show_diagnostics)
        QWidget.setTabOrder(self.show_diagnostics, self.show_raw)

        self._sync_response_mode(self.include_llm_answer.isChecked())
        self._refresh_selected_documents_label()
        self._refresh_document_catalog_state()
        QTimer.singleShot(0, self._refresh_document_catalog_silent)
        self.question.setFocus()

    def _run_query(self) -> None:
        validation_error = self._validate_inputs()
        if validation_error:
            self._set_status("error", validation_error)
            self.answer.setPlainText(
                "Error de validacion. Revisa el formulario e intenta nuevamente."
            )
            return

        payload = {
            "question": self.question.text().strip(),
            "source_id": self.source_id.text().strip() or None,
            "document_ids": self.selected_document_ids(),
            "hops": self._safe_int(self.hops.text().strip()),
            "include_llm_answer": self.include_llm_answer.isChecked(),
        }

        self._set_status("running", "Ejecutando consulta...")
        result = self._on_query(payload)
        if "answer" in result:
            pretty = {
                "answer": result.get("answer"),
                "diagnostics": result.get("diagnostics", {}),
            }
            answer_text = (result.get("answer") or "").strip()
            if not answer_text:
                answer_text = (
                    "No se recibio respuesta LLM. Revisa citas y diagnosticos."
                )
            self.answer.setPlainText(answer_text)
            self.diagnostics.setPlainText(
                json.dumps(pretty.get("diagnostics", {}), indent=2, ensure_ascii=False)
            )
            self.raw_response.setPlainText(
                json.dumps(result, indent=2, ensure_ascii=False)
            )
            self.evidence.update_evidence(
                result.get("citations", []),
                result.get("graph_paths", []),
            )
            self._set_status("success", "Consulta completada")
        else:
            error_text = self._build_actionable_error(result)
            self.answer.setPlainText(error_text)
            self.diagnostics.setPlainText(
                json.dumps(result.get("diagnostics", result), indent=2, ensure_ascii=False)
            )
            self.raw_response.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))
            self._set_status("error", "Consulta fallida")

    def _validate_inputs(self) -> str | None:
        """Validate query form fields before calling backend."""
        question = (self.question.text() or "").strip()
        hops = (self.hops.text() or "").strip()

        if not question:
            self.question.setProperty("invalid", True)
            self._refresh_input_style(self.question)
            return "La pregunta es obligatoria."

        self.question.setProperty("invalid", False)
        self._refresh_input_style(self.question)

        parsed_hops = self._safe_int(hops)
        is_invalid_hops = parsed_hops is None or parsed_hops < 1 or parsed_hops > 6
        self.hops.setProperty("invalid", is_invalid_hops)
        self._refresh_input_style(self.hops)
        if is_invalid_hops:
            return "Los saltos de grafo deben ser un entero entre 1 y 6."

        return None

    @staticmethod
    def _build_actionable_error(result: dict) -> str:
        """Compose a readable, actionable error message for failed queries."""
        detail = str(result.get("detail") or result.get("error") or "").strip()
        if not detail:
            detail = "La consulta no pudo completarse por un error desconocido."
        return (
            "La consulta fallo.\n"
            f"Detalle: {detail}\n"
            "Accion sugerida: verifica API activa, parametros de entrada y estado de indices."
        )

    def _set_status(self, state: str, text: str) -> None:
        """Set status badge token and visible status text."""
        label_by_state = {
            "idle": "inactivo",
            "running": "en curso",
            "success": "ok",
            "error": "error",
        }
        self.status_label.setProperty("state", state)
        self.status_label.setText(label_by_state.get(state, "inactivo"))
        self.status_message.setText(text)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.update()

    def _sync_response_mode(self, checked: bool) -> None:
        """Render a clear visual badge for LLM response mode state."""
        badge_state = "success" if checked else "idle"
        badge_text = "LLM activo" if checked else "LLM inactivo"
        self.response_mode_badge.setProperty("state", badge_state)
        self.response_mode_badge.setText(badge_text)
        self.response_mode_badge.style().unpolish(self.response_mode_badge)
        self.response_mode_badge.style().polish(self.response_mode_badge)
        self.response_mode_badge.update()

    def _toggle_diagnostics(self, checked: bool) -> None:
        """Toggle diagnostics panel visibility."""
        self.diagnostics_label.setVisible(checked)
        self.diagnostics.setVisible(checked)

    def _toggle_raw(self, checked: bool) -> None:
        """Toggle raw JSON panel visibility."""
        self.raw_label.setVisible(checked)
        self.raw_response.setVisible(checked)

    @staticmethod
    def _refresh_input_style(widget: QLineEdit) -> None:
        """Re-apply stylesheet when dynamic input state changes."""
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    @staticmethod
    def _safe_int(raw: str) -> int | None:
        try:
            return int(raw)
        except ValueError:
            return None

    def _open_document_picker(self) -> None:
        """Load ingested documents and let the user multi-select them."""
        if not self._ensure_document_catalog(show_feedback=True):
            return

        dialog = DocumentPickerDialog(
            documents=self._available_documents,
            selected_ids=self.selected_document_ids(),
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._set_selected_documents(dialog.selected_documents())
            self._set_status("idle", "Filtro de documentos actualizado")

    def _handle_source_id_change(self, raw_text: str) -> None:
        """Keep selected documents consistent with the current source filter."""
        source_id = raw_text.strip()
        self._document_refresh_timer.start()
        if not self._selected_documents:
            self._refresh_document_catalog_state()
            return

        if not source_id:
            self._refresh_document_catalog_state()
            return

        kept_documents = [
            item
            for item in self._selected_documents
            if str(item.get("source_id") or "").strip() == source_id
        ]
        if len(kept_documents) == len(self._selected_documents):
            return

        self._selected_documents = kept_documents
        self._refresh_selected_documents_label()
        self._set_status(
            "idle",
            "Filtro de documentos ajustado al Source ID actual",
        )
        self._refresh_document_catalog_state()

    def _clear_selected_documents(self) -> None:
        """Reset the optional document filter to query all documents."""
        self._selected_documents = []
        self._refresh_selected_documents_label()
        self._refresh_document_catalog_state()

    def _delete_selected_documents(self) -> None:
        """Delete the currently selected documents after explicit confirmation."""
        if self._on_delete_document is None:
            self._set_status(
                "error",
                "La sesion actual no expone borrado manual de documentos.",
            )
            return

        documents = list(self._selected_documents)
        if not documents:
            self._set_status(
                "error",
                "Selecciona uno o mas documentos antes de eliminarlos.",
            )
            return

        preview = ", ".join(
            str(item.get("title") or item.get("document_id") or "")
            for item in documents[:3]
        )
        if len(documents) > 3:
            preview += f" y {len(documents) - 3} mas"

        decision = QMessageBox.question(
            self,
            "Confirmar borrado de documentos",
            (
                "Esta accion eliminara de forma persistente los documentos "
                f"seleccionados ({len(documents)}).\n\n{preview}\n\n"
                "Se borraran metadatos, chunks, vectores y mirror de staging "
                "cuando aplique."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if decision != QMessageBox.StandardButton.Yes:
            return

        deleted_ids: list[str] = []
        failed_documents: list[str] = []
        for item in documents:
            document_id = str(item.get("document_id") or "").strip()
            if not document_id:
                continue
            result = self._on_delete_document(document_id)
            if "error" in result or "detail" in result:
                failed_documents.append(
                    str(item.get("title") or document_id)
                )
                continue
            deleted_ids.append(document_id)

        if deleted_ids:
            deleted_set = set(deleted_ids)
            self._available_documents = [
                item
                for item in self._available_documents
                if str(item.get("document_id") or "") not in deleted_set
            ]
            self._selected_documents = [
                item
                for item in self._selected_documents
                if str(item.get("document_id") or "") not in deleted_set
            ]
            self._refresh_selected_documents_label()
            if self._on_list_documents is not None:
                self._refresh_document_catalog(show_feedback=False)
            else:
                self._refresh_document_catalog_state()

        if deleted_ids and not failed_documents:
            self._set_status(
                "success",
                f"Documentos eliminados: {len(deleted_ids)}",
            )
            return

        if deleted_ids and failed_documents:
            self._set_status(
                "error",
                (
                    f"Se eliminaron {len(deleted_ids)} documentos, pero "
                    f"fallaron {len(failed_documents)}."
                ),
            )
            return

        self._set_status(
            "error",
            "No se pudo eliminar ninguno de los documentos seleccionados.",
        )

    def _set_selected_documents(
        self,
        documents: Sequence[dict[str, Any]],
    ) -> None:
        """Store a normalized list of selected document metadata rows."""
        normalized: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for item in documents:
            if not isinstance(item, dict):
                continue
            document_id = str(item.get("document_id") or "").strip()
            if not document_id or document_id in seen_ids:
                continue
            seen_ids.add(document_id)
            normalized.append(
                {
                    "document_id": document_id,
                    "title": str(item.get("title") or document_id),
                    "path_or_url": str(item.get("path_or_url") or ""),
                    "source_id": str(item.get("source_id") or ""),
                }
            )
        self._selected_documents = normalized
        self._refresh_selected_documents_label()
        self._refresh_document_catalog_state()

    def _refresh_selected_documents_label(self) -> None:
        """Render a compact human-readable summary of document filter state."""
        if not self._selected_documents:
            self.selected_documents_label.setText("Sin filtro por documento")
            return

        labels = [
            str(item.get("title") or item.get("document_id") or "")
            for item in self._selected_documents
        ]
        if len(labels) == 1:
            summary = labels[0]
        elif len(labels) == 2:
            summary = f"{labels[0]} y {labels[1]}"
        else:
            summary = f"{labels[0]}, {labels[1]} y {len(labels) - 2} mas"
        self.selected_documents_label.setText(summary)

    def selected_document_ids(self) -> list[str]:
        """Return selected document ids in UI order for payload wiring."""
        return [
            str(item.get("document_id") or "")
            for item in self._selected_documents
            if str(item.get("document_id") or "")
        ]

    def _refresh_document_catalog_silent(self) -> None:
        """Refresh available document catalog without noisy user messaging."""
        self._refresh_document_catalog(show_feedback=False)

    def _refresh_document_catalog(self, show_feedback: bool) -> bool:
        """Fetch the current document catalog and sync picker state."""
        if self._on_list_documents is None:
            self._available_documents = []
            self._refresh_document_catalog_state(unavailable=True)
            if show_feedback:
                self._set_status(
                    "error",
                    "El catalogo de documentos no esta disponible en esta sesion.",
                )
            return False

        source_id = self.source_id.text().strip() or None
        result = self._on_list_documents(source_id)
        documents = result.get("documents", []) if isinstance(result, dict) else []
        if not isinstance(documents, list):
            documents = []

        self._available_documents = [
            item for item in documents if isinstance(item, dict)
        ]
        self._prune_selected_documents_against_catalog()
        self._refresh_document_catalog_state()

        if show_feedback:
            if self._available_documents:
                self._set_status(
                    "idle",
                    f"Catalogo actualizado: {len(self._available_documents)} documentos",
                )
            else:
                self._set_status(
                    "error",
                    "No hay documentos ingestados para la fuente seleccionada.",
                )
        return bool(self._available_documents)

    def _ensure_document_catalog(self, show_feedback: bool) -> bool:
        """Ensure a non-empty cached catalog exists before opening picker."""
        source_id = self.source_id.text().strip() or None
        if self._available_documents:
            cached_source_ids = {
                str(item.get("source_id") or "").strip()
                for item in self._available_documents
            }
            if not source_id or cached_source_ids == {source_id}:
                return True
        return self._refresh_document_catalog(show_feedback=show_feedback)

    def _prune_selected_documents_against_catalog(self) -> None:
        """Remove selected documents that are no longer present in catalog."""
        if not self._selected_documents:
            return
        allowed_ids = {
            str(item.get("document_id") or "")
            for item in self._available_documents
            if str(item.get("document_id") or "")
        }
        if not allowed_ids:
            self._selected_documents = []
            self._refresh_selected_documents_label()
            return
        kept = [
            item
            for item in self._selected_documents
            if str(item.get("document_id") or "") in allowed_ids
        ]
        if len(kept) != len(self._selected_documents):
            self._selected_documents = kept
            self._refresh_selected_documents_label()

    def _refresh_document_catalog_state(self, unavailable: bool = False) -> None:
        """Render current picker availability and scope state."""
        if unavailable:
            self.document_catalog_label.setProperty("state", "error")
            self.document_catalog_label.setText("Catalogo no disponible")
            self.document_picker_button.setEnabled(False)
            self.document_refresh_button.setEnabled(False)
            return

        source_id = self.source_id.text().strip()
        document_count = len(self._available_documents)
        selected_count = len(self.selected_document_ids())
        self.document_refresh_button.setEnabled(self._on_list_documents is not None)
        self.document_picker_button.setEnabled(document_count > 0)
        self.delete_documents_button.setEnabled(
            self._on_delete_document is not None and selected_count > 0
        )

        if document_count <= 0:
            self.document_catalog_label.setProperty("state", "idle")
            if source_id:
                self.document_catalog_label.setText("0 docs en source")
            else:
                self.document_catalog_label.setText("Catalogo vacio")
        else:
            self.document_catalog_label.setProperty("state", "success")
            if selected_count > 0:
                self.document_catalog_label.setText(
                    f"{selected_count}/{document_count} seleccionados"
                )
            elif source_id:
                self.document_catalog_label.setText(
                    f"{document_count} docs en source"
                )
            else:
                self.document_catalog_label.setText(
                    f"{document_count} docs disponibles"
                )

        self.document_catalog_label.style().unpolish(self.document_catalog_label)
        self.document_catalog_label.style().polish(self.document_catalog_label)
        self.document_catalog_label.update()
