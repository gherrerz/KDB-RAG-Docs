"""Query panel for asking grounded questions."""

from __future__ import annotations

import json
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from coderag.ui.evidence_view import EvidenceView


class QueryView(QWidget):
    """Widget for querying backend and presenting evidence."""

    def __init__(self, on_query: Callable[[dict], dict]) -> None:
        super().__init__()
        self._on_query = on_query

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
        self.hops.setPlaceholderText("1-6")
        self.hops.setToolTip(
            "Profundidad de expansion del grafo. Recomendado: 2."
        )

        form.addRow("Pregunta", self.question)
        form.addRow("Source ID (opcional)", self.source_id)
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
        QWidget.setTabOrder(self.source_id, self.hops)
        QWidget.setTabOrder(self.hops, self.include_llm_answer)
        QWidget.setTabOrder(self.include_llm_answer, self.query_button)
        QWidget.setTabOrder(self.query_button, self.show_diagnostics)
        QWidget.setTabOrder(self.show_diagnostics, self.show_raw)

        self._sync_response_mode(self.include_llm_answer.isChecked())
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
