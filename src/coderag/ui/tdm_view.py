"""TDM panel for additive catalog and planning endpoints."""

from __future__ import annotations

import json
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolBox,
    QVBoxLayout,
    QWidget,
    QApplication,
)


class TdmView(QWidget):
    """Widget for invoking additive TDM endpoints from the desktop UI."""

    def __init__(
        self,
        on_tdm_ingest: Callable[[dict[str, Any]], dict[str, Any]],
        on_tdm_query: Callable[[dict[str, Any]], dict[str, Any]],
        on_tdm_service_catalog: Callable[[str, str | None], dict[str, Any]],
        on_tdm_table_catalog: Callable[[str, str | None], dict[str, Any]],
        on_tdm_virtualization_preview: Callable[[dict[str, Any]], dict[str, Any]],
        on_tdm_synthetic_profile: Callable[[str, str | None, int], dict[str, Any]],
    ) -> None:
        super().__init__()
        self._on_tdm_ingest = on_tdm_ingest
        self._on_tdm_query = on_tdm_query
        self._on_tdm_service_catalog = on_tdm_service_catalog
        self._on_tdm_table_catalog = on_tdm_table_catalog
        self._on_tdm_virtualization_preview = on_tdm_virtualization_preview
        self._on_tdm_synthetic_profile = on_tdm_synthetic_profile

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_content = QWidget()
        content = QVBoxLayout(scroll_content)
        content.setContentsMargins(12, 12, 12, 12)
        content.setSpacing(10)
        scroll.setWidget(scroll_content)
        root.addWidget(scroll)

        ingest_group = QGroupBox("TDM Ingest")
        ingest_form = QFormLayout(ingest_group)
        ingest_form.setHorizontalSpacing(12)
        ingest_form.setVerticalSpacing(10)
        ingest_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)

        self.source_type = QLineEdit("tdm_folder")
        self.source_type.setMinimumHeight(34)
        self.source_type.setPlaceholderText("tdm_folder")
        self.local_path = QLineEdit("sample_data")
        self.local_path.setMinimumHeight(34)
        self.local_path.setClearButtonEnabled(True)
        self.filters = QLineEdit("{}")
        self.filters.setMinimumHeight(34)
        self.filters.setPlaceholderText('{"domain": "billing"}')

        ingest_form.addRow("Source type", self.source_type)
        ingest_form.addRow("Local path", self.local_path)
        ingest_form.addRow("Filters (JSON)", self.filters)

        query_group = QGroupBox("Consulta y catalogo TDM")
        query_form = QFormLayout(query_group)
        query_form.setHorizontalSpacing(12)
        query_form.setVerticalSpacing(10)
        query_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)

        self.question = QLineEdit()
        self.question.setMinimumHeight(34)
        self.question.setPlaceholderText("que tablas usa billing-api")
        self.source_id = QLineEdit()
        self.source_id.setMinimumHeight(34)
        self.source_id.setPlaceholderText("source_id opcional")
        self.service_name = QLineEdit()
        self.service_name.setMinimumHeight(34)
        self.service_name.setPlaceholderText("billing-api")
        self.table_name = QLineEdit()
        self.table_name.setMinimumHeight(34)
        self.table_name.setPlaceholderText("invoices")
        self.include_virtualization_preview = QCheckBox(
            "Incluir virtualization preview en /tdm/query"
        )

        self.target_rows = QLineEdit("1000")
        self.target_rows.setMinimumHeight(34)
        self.target_rows.setValidator(QIntValidator(1, 10_000_000, self))

        query_form.addRow("Question", self.question)
        query_form.addRow("Source ID", self.source_id)
        query_form.addRow("Service", self.service_name)
        query_form.addRow("Table", self.table_name)
        query_form.addRow("Synthetic target rows", self.target_rows)
        query_form.addRow("Options", self.include_virtualization_preview)

        query_actions_group = QGroupBox("Operaciones de consulta")
        query_actions = QHBoxLayout(query_actions_group)
        self.ingest_button = QPushButton("Ingerir TDM")
        self.ingest_button.setProperty("variant", "primary")
        self.ingest_button.clicked.connect(self._run_tdm_ingest)

        self.query_button = QPushButton("Consultar TDM")
        self.query_button.setProperty("variant", "primary")
        self.query_button.clicked.connect(self._run_tdm_query)

        query_actions.addWidget(self.ingest_button)
        query_actions.addWidget(self.query_button)

        catalog_actions_group = QGroupBox("Catalogo TDM")
        catalog_actions = QHBoxLayout(catalog_actions_group)

        self.service_catalog_button = QPushButton("Catalogo por servicio")
        self.service_catalog_button.clicked.connect(self._run_service_catalog)
        self.table_catalog_button = QPushButton("Catalogo por tabla")
        self.table_catalog_button.clicked.connect(self._run_table_catalog)

        catalog_actions.addWidget(self.service_catalog_button)
        catalog_actions.addWidget(self.table_catalog_button)

        planning_actions_group = QGroupBox("Planning TDM")
        planning_actions = QHBoxLayout(planning_actions_group)
        self.virtualization_button = QPushButton("Preview de virtualizacion")
        self.virtualization_button.clicked.connect(self._run_virtualization_preview)
        self.synthetic_button = QPushButton("Perfil sintetico")
        self.synthetic_button.clicked.connect(self._run_synthetic_profile)

        planning_actions.addWidget(self.virtualization_button)
        planning_actions.addWidget(self.synthetic_button)

        sections = QToolBox()
        sections.addItem(ingest_group, "1. Ingesta")
        sections.addItem(query_group, "2. Contexto de consulta")
        sections.addItem(query_actions_group, "3. Ejecutar consulta")
        sections.addItem(catalog_actions_group, "4. Catalogo")
        sections.addItem(planning_actions_group, "5. Planning")
        sections.setCurrentIndex(1)

        self.status_label = QLabel("inactivo")
        self.status_label.setProperty("role", "status")
        self.status_label.setProperty("state", "idle")
        self.status_hint = QLabel("Listo para operaciones TDM")
        self.status_hint.setProperty("role", "hint")

        status_row = QHBoxLayout()
        status_row.addWidget(self.status_label)
        status_row.addWidget(self.status_hint)
        status_row.addStretch(1)

        table_tools = QGroupBox("Resultados TDM")
        table_tools_layout = QHBoxLayout(table_tools)
        self.result_type_filter = QComboBox()
        self.result_type_filter.setMinimumHeight(32)
        self.result_type_filter.addItem("Todos los tipos", "")
        self.result_type_filter.currentIndexChanged.connect(
            self._apply_current_filters
        )
        self.result_filter = QLineEdit()
        self.result_filter.setMinimumHeight(32)
        self.result_filter.setPlaceholderText(
            "Filtrar filas por texto (type/service/table/notes)"
        )
        self.result_filter.textChanged.connect(self._apply_current_filters)
        self.export_visible_button = QPushButton("Exportar filas visibles")
        self.export_visible_button.clicked.connect(self._export_visible_rows_to_raw)
        self.copy_row_json_button = QPushButton("Copiar JSON de fila")
        self.copy_row_json_button.clicked.connect(self._copy_selected_row_json)
        self.copy_endpoint_button = QPushButton("Copiar endpoint/metodo")
        self.copy_endpoint_button.clicked.connect(self._copy_selected_endpoint_method)
        self.load_row_raw_button = QPushButton("Cargar fila en raw")
        self.load_row_raw_button.clicked.connect(self._load_selected_row_raw)
        self.result_count_label = QLabel("0 filas")
        self.result_count_label.setProperty("role", "hint")
        self.shortcuts_hint = QLabel(
            "Atajos: Ctrl+Shift+C copiar JSON | Ctrl+Shift+E endpoint/metodo | "
            "Ctrl+Shift+L cargar raw | Ctrl+Shift+X export visible"
        )
        self.shortcuts_hint.setProperty("role", "hint")
        self.shortcuts_hint.setWordWrap(True)
        self.export_visible_button.setToolTip("Atajo: Ctrl+Shift+X")
        self.copy_row_json_button.setToolTip("Atajo: Ctrl+Shift+C")
        self.copy_endpoint_button.setToolTip("Atajo: Ctrl+Shift+E")
        self.load_row_raw_button.setToolTip("Atajo: Ctrl+Shift+L")
        table_tools_layout.addWidget(self.result_type_filter)
        table_tools_layout.addWidget(self.result_filter)
        table_tools_layout.addWidget(self.export_visible_button)
        table_tools_layout.addWidget(self.copy_row_json_button)
        table_tools_layout.addWidget(self.copy_endpoint_button)
        table_tools_layout.addWidget(self.load_row_raw_button)
        table_tools_layout.addWidget(self.result_count_label)

        self.show_raw = QCheckBox("Mostrar JSON crudo")
        self.show_raw.setChecked(True)
        self.show_raw.toggled.connect(self._toggle_raw)

        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setPlainText(
            "Estado: inactivo\n"
            "Flujo legacy no cambia; usa esta pestaña para endpoints /tdm/*."
        )

        self.raw = QTextEdit()
        self.raw.setReadOnly(True)

        self.result_table = QTableWidget(0, 4)
        self.result_table.setHorizontalHeaderLabels(
            ["Tipo", "Principal", "Secundario", "Notas"]
        )
        self.result_table.setAlternatingRowColors(True)
        self.result_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.result_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.result_table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self.result_table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self.result_table.horizontalHeader().setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self.result_table.setSortingEnabled(True)
        self.result_table.itemSelectionChanged.connect(
            self._render_selected_result_detail
        )

        self.result_detail = QTextEdit()
        self.result_detail.setReadOnly(True)
        self.result_detail.setPlaceholderText(
            "Selecciona una fila para ver detalles estructurados del resultado TDM."
        )
        self._result_rows: list[dict[str, Any]] = []
        self._visible_result_rows: list[dict[str, Any]] = []

        # Keep shortcuts explicit in one place for discoverability and tests.
        self._shortcuts: dict[str, QShortcut] = {
            "export_visible": QShortcut(
                QKeySequence("Ctrl+Shift+X"),
                self,
            ),
            "copy_row_json": QShortcut(
                QKeySequence("Ctrl+Shift+C"),
                self,
            ),
            "copy_endpoint": QShortcut(
                QKeySequence("Ctrl+Shift+E"),
                self,
            ),
            "load_row_raw": QShortcut(
                QKeySequence("Ctrl+Shift+L"),
                self,
            ),
        }
        self._shortcuts["export_visible"].activated.connect(
            self._export_visible_rows_to_raw
        )
        self._shortcuts["copy_row_json"].activated.connect(
            self._copy_selected_row_json
        )
        self._shortcuts["copy_endpoint"].activated.connect(
            self._copy_selected_endpoint_method
        )
        self._shortcuts["load_row_raw"].activated.connect(
            self._load_selected_row_raw
        )

        feedback = QSplitter(Qt.Orientation.Vertical)
        feedback.addWidget(self.summary)
        feedback.addWidget(self.result_table)
        feedback.addWidget(self.result_detail)
        feedback.addWidget(self.raw)
        feedback.setChildrenCollapsible(False)
        feedback.setStretchFactor(0, 1)
        feedback.setStretchFactor(1, 3)
        feedback.setStretchFactor(2, 2)
        feedback.setStretchFactor(3, 1)
        feedback.setSizes([130, 300, 200, 180])

        content.addWidget(sections)
        content.addLayout(status_row)
        content.addWidget(table_tools)
        content.addWidget(self.shortcuts_hint)
        content.addWidget(self.show_raw)
        content.addWidget(feedback)

    def _run_tdm_ingest(self) -> None:
        """Build payload and invoke TDM ingest endpoint."""
        source_type = self.source_type.text().strip() or "tdm_folder"
        local_path = self.local_path.text().strip()
        if not local_path:
            self._set_error("El campo Local path es obligatorio para TDM ingest.")
            return

        self._set_status("running", "Ejecutando ingesta TDM...")
        payload = {
            "source": {
                "source_type": source_type,
                "local_path": local_path,
                "filters": self._safe_json(self.filters.text().strip()),
            }
        }
        result = self._on_tdm_ingest(payload)
        self._render_result("/tdm/ingest", result)

    def _run_tdm_query(self) -> None:
        """Build payload and invoke TDM query endpoint."""
        question = self.question.text().strip()
        if not question:
            self._set_error("La pregunta es obligatoria para /tdm/query.")
            return

        self._set_status("running", "Ejecutando consulta TDM...")
        payload = {
            "question": question,
            "source_id": self._optional(self.source_id.text()),
            "service_name": self._optional(self.service_name.text()),
            "table_name": self._optional(self.table_name.text()),
            "include_virtualization_preview": self.include_virtualization_preview.isChecked(),
        }
        result = self._on_tdm_query(payload)
        self._render_result("/tdm/query", result)

    def _run_service_catalog(self) -> None:
        """Invoke TDM service catalog endpoint."""
        service_name = self.service_name.text().strip()
        if not service_name:
            self._set_error("El nombre de servicio es obligatorio para el catalogo por servicio.")
            return
        self._set_status("running", "Consultando catalogo por servicio...")
        result = self._on_tdm_service_catalog(
            service_name,
            self._optional(self.source_id.text()),
        )
        self._render_result("/tdm/catalog/services/{service_name}", result)

    def _run_table_catalog(self) -> None:
        """Invoke TDM table catalog endpoint."""
        table_name = self.table_name.text().strip()
        if not table_name:
            self._set_error("El nombre de tabla es obligatorio para el catalogo por tabla.")
            return
        self._set_status("running", "Consultando catalogo por tabla...")
        result = self._on_tdm_table_catalog(
            table_name,
            self._optional(self.source_id.text()),
        )
        self._render_result("/tdm/catalog/tables/{table_name}", result)

    def _run_virtualization_preview(self) -> None:
        """Invoke TDM virtualization preview endpoint."""
        question = self.question.text().strip()
        self._set_status("running", "Generando preview de virtualizacion...")
        payload = {
            "question": question or "virtualization preview",
            "source_id": self._optional(self.source_id.text()),
            "service_name": self._optional(self.service_name.text()),
            "table_name": self._optional(self.table_name.text()),
            "include_virtualization_preview": True,
        }
        result = self._on_tdm_virtualization_preview(payload)
        self._render_result("/tdm/virtualization/preview", result)

    def _run_synthetic_profile(self) -> None:
        """Invoke TDM synthetic profile endpoint."""
        table_name = self.table_name.text().strip()
        if not table_name:
            self._set_error("El nombre de tabla es obligatorio para synthetic profile.")
            return

        rows = self._safe_int(self.target_rows.text().strip())
        if rows is None or rows < 1:
            self._set_error("Synthetic target rows debe ser un entero >= 1.")
            return

        self._set_status("running", "Generando perfil sintetico...")
        result = self._on_tdm_synthetic_profile(
            table_name,
            self._optional(self.source_id.text()),
            rows,
        )
        self._render_result("/tdm/synthetic/profile/{table_name}", result)

    def _render_result(self, operation: str, result: dict[str, Any]) -> None:
        """Render operation result with capability-aware status messaging."""
        detail = str(result.get("detail") or result.get("error") or "").strip()
        if detail:
            self._set_status("error", self._hint_for_error_detail(detail))
            self.summary.setPlainText(
                "Estado: failed\n"
                f"Operacion: {operation}\n"
                f"Detalle: {detail}"
            )
        else:
            findings = result.get("findings")
            count = result.get("count")
            has_empty_findings = isinstance(findings, list) and len(findings) == 0
            has_empty_count = isinstance(count, int) and count == 0

            if has_empty_findings or has_empty_count:
                self._set_status(
                    "success",
                    "Operacion completada sin resultados; ajusta filtros o source_id.",
                )
            else:
                self._set_status("success", "Operacion TDM completada")

            findings = result.get("findings")
            count = result.get("count")
            findings_count = len(findings) if isinstance(findings, list) else "n/a"
            self.summary.setPlainText(
                "Estado: completed\n"
                f"Operacion: {operation}\n"
                f"Count: {count if count is not None else 'n/a'}\n"
                f"Findings: {findings_count}"
            )

        self._update_result_table(result)

        self.raw.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))

    def _update_result_table(self, result: dict[str, Any]) -> None:
        """Render structured result rows for operational review."""
        rows = self._extract_result_rows(result)
        self._result_rows = rows
        self._refresh_result_type_filter_options(rows)
        self._visible_result_rows = rows
        self._render_result_rows(rows)
        self._update_result_count(len(rows))

    def _render_result_rows(self, rows: list[dict[str, Any]]) -> None:
        """Paint one list of result rows into the table widget."""
        self.result_table.setSortingEnabled(False)
        self.result_table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            values = [
                str(row.get("type", "")),
                str(row.get("primary", "")),
                str(row.get("secondary", "")),
                str(row.get("notes", "")),
            ]
            for col_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(
                    Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                )
                self.result_table.setItem(row_index, col_index, item)

        self.result_table.setSortingEnabled(True)

        if self.result_table.rowCount() > 0:
            self.result_table.selectRow(0)
        else:
            self.result_detail.setPlainText(
                "Sin filas estructuradas para mostrar en esta operacion."
            )

    def _render_selected_result_detail(self) -> None:
        """Show JSON detail for the selected operational row."""
        selected = self.result_table.selectedItems()
        if not selected:
            self.result_detail.setPlainText(
                "Selecciona una fila para ver detalles estructurados."
            )
            return

        row_index = selected[0].row()
        if row_index < 0 or row_index >= len(self._visible_result_rows):
            self.result_detail.setPlainText("Detalle no disponible.")
            return

        self.result_detail.setPlainText(
            json.dumps(
                self._visible_result_rows[row_index],
                indent=2,
                ensure_ascii=False,
            )
        )

    def _apply_current_filters(self, *_: object) -> None:
        """Apply type and text filters together over structured rows."""
        normalized_text = self.result_filter.text().strip().casefold()
        selected_type = str(self.result_type_filter.currentData() or "")

        filtered = []
        for row in self._result_rows:
            row_type = str(row.get("type", ""))
            if selected_type and row_type != selected_type:
                continue

            if normalized_text:
                haystack = " ".join(
                    [
                        row_type,
                        str(row.get("primary", "")),
                        str(row.get("secondary", "")),
                        str(row.get("notes", "")),
                    ]
                ).casefold()
                if normalized_text not in haystack:
                    continue

            filtered.append(row)

        self._visible_result_rows = filtered
        self._render_result_rows(filtered)
        self._update_result_count(len(filtered))

    def _refresh_result_type_filter_options(
        self,
        rows: list[dict[str, Any]],
    ) -> None:
        """Refresh available result types for the type selector."""
        current_data = str(self.result_type_filter.currentData() or "")
        types = sorted(
            {
                str(row.get("type", "")).strip()
                for row in rows
                if str(row.get("type", "")).strip()
            }
        )

        self.result_type_filter.blockSignals(True)
        self.result_type_filter.clear()
        self.result_type_filter.addItem("Todos los tipos", "")
        for type_name in types:
            self.result_type_filter.addItem(type_name, type_name)

        restore_index = 0
        if current_data:
            for idx in range(self.result_type_filter.count()):
                if str(self.result_type_filter.itemData(idx) or "") == current_data:
                    restore_index = idx
                    break
        self.result_type_filter.setCurrentIndex(restore_index)
        self.result_type_filter.blockSignals(False)

    def _export_visible_rows_to_raw(self) -> None:
        """Export currently visible structured rows as JSON into raw panel."""
        exported = {
            "export_type": "tdm_visible_rows",
            "count": len(self._visible_result_rows),
            "rows": self._visible_result_rows,
        }
        self.raw.setPlainText(json.dumps(exported, indent=2, ensure_ascii=False))
        self._set_status("success", "Filas visibles exportadas a JSON crudo.")

    def _update_result_count(self, count: int) -> None:
        """Update counter label for currently visible result rows."""
        suffix = "fila" if count == 1 else "filas"
        self.result_count_label.setText(f"{count} {suffix}")

    def _selected_result_row(self) -> dict[str, Any] | None:
        """Return selected visible row payload or None when unavailable."""
        selected = self.result_table.selectedItems()
        if not selected:
            return None
        row_index = selected[0].row()
        if row_index < 0 or row_index >= len(self._visible_result_rows):
            return None
        return self._visible_result_rows[row_index]

    def _copy_selected_row_json(self) -> None:
        """Copy selected structured row as JSON into clipboard."""
        row = self._selected_result_row()
        if row is None:
            self._set_status("error", "Selecciona una fila para copiar JSON.")
            return

        text = json.dumps(row, indent=2, ensure_ascii=False)
        QApplication.clipboard().setText(text)
        self._set_status("success", "Fila seleccionada copiada a clipboard.")

    def _copy_selected_endpoint_method(self) -> None:
        """Copy endpoint/method shortcut from selected row when available."""
        row = self._selected_result_row()
        if row is None:
            self._set_status("error", "Selecciona una fila para copiar endpoint.")
            return

        payload = row.get("raw")
        if not isinstance(payload, dict):
            self._set_status("error", "Fila sin payload util para endpoint.")
            return

        endpoint = str(payload.get("endpoint") or "").strip()
        method = str(payload.get("method") or "").strip().upper()

        if not endpoint:
            content = str(row.get("secondary") or "").strip()
            if content.startswith("/"):
                endpoint = content
        if not method:
            note = str(row.get("notes") or "").strip().upper()
            if note in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
                method = note

        if not endpoint and not method:
            self._set_status("error", "No hay endpoint/metodo en la fila seleccionada.")
            return

        clipboard_text = f"{method} {endpoint}".strip()
        QApplication.clipboard().setText(clipboard_text)
        self._set_status("success", "Endpoint/metodo copiado a clipboard.")

    def _load_selected_row_raw(self) -> None:
        """Load selected row payload into raw JSON panel."""
        row = self._selected_result_row()
        if row is None:
            self._set_status("error", "Selecciona una fila para cargar raw.")
            return

        self.raw.setPlainText(json.dumps(row, indent=2, ensure_ascii=False))
        self._set_status("success", "Fila seleccionada cargada en JSON crudo.")

    @staticmethod
    def _extract_result_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
        """Normalize response payloads into rows for tabular rendering."""
        rows: list[dict[str, Any]] = []

        findings = result.get("findings")
        if isinstance(findings, list):
            for finding in findings:
                if not isinstance(finding, dict):
                    continue
                rows.append(
                    {
                        "type": "finding",
                        "primary": str(
                            finding.get("service_name")
                            or finding.get("table_name")
                            or finding.get("column_name")
                            or finding.get("mapping_id")
                            or "item"
                        ),
                        "secondary": str(
                            finding.get("endpoint")
                            or finding.get("table_id")
                            or finding.get("data_type")
                            or ""
                        ),
                        "notes": str(
                            finding.get("method")
                            or finding.get("pii_class")
                            or ""
                        ),
                        "raw": finding,
                    }
                )

        mappings = result.get("mappings")
        if isinstance(mappings, list):
            for mapping in mappings:
                if not isinstance(mapping, dict):
                    continue
                rows.append(
                    {
                        "type": "service_mapping",
                        "primary": str(mapping.get("service_name") or ""),
                        "secondary": str(mapping.get("endpoint") or ""),
                        "notes": str(mapping.get("method") or ""),
                        "raw": mapping,
                    }
                )

        tables = result.get("tables")
        if isinstance(tables, list):
            for table in tables:
                if not isinstance(table, dict):
                    continue
                rows.append(
                    {
                        "type": "table",
                        "primary": str(table.get("table_name") or ""),
                        "secondary": str(table.get("table_id") or ""),
                        "notes": str(table.get("schema_id") or ""),
                        "raw": table,
                    }
                )

        columns = result.get("columns")
        if isinstance(columns, list):
            for column in columns:
                if not isinstance(column, dict):
                    continue
                rows.append(
                    {
                        "type": "column",
                        "primary": str(column.get("column_name") or ""),
                        "secondary": str(column.get("data_type") or ""),
                        "notes": str(column.get("pii_class") or ""),
                        "raw": column,
                    }
                )

        templates = result.get("templates")
        if isinstance(templates, list):
            for template in templates:
                if not isinstance(template, dict):
                    continue
                request = template.get("content", {}).get("request", {})
                if not isinstance(request, dict):
                    request = {}
                rows.append(
                    {
                        "type": "virtualization",
                        "primary": str(template.get("service_name") or ""),
                        "secondary": str(request.get("path") or ""),
                        "notes": str(request.get("method") or ""),
                        "raw": template,
                    }
                )

        plan = result.get("plan")
        if isinstance(plan, dict):
            rows.append(
                {
                    "type": "synthetic_plan",
                    "primary": str(plan.get("table_name") or result.get("table_name") or ""),
                    "secondary": str(plan.get("target_rows") or ""),
                    "notes": str(plan.get("strategy") or ""),
                    "raw": plan,
                }
            )

        return rows

    def _set_error(self, message: str) -> None:
        """Render local validation error without backend call."""
        self._set_status("error", "Error de validacion en el formulario.")
        self.summary.setPlainText(f"Estado: failed\nDetalle: {message}")

    @staticmethod
    def _hint_for_error_detail(detail: str) -> str:
        """Map backend error details into actionable UI hints."""
        lowered = detail.casefold()
        if "tdm endpoints are disabled" in lowered:
            return "TDM deshabilitado (ENABLE_TDM=false)."
        if "tdm virtualization is disabled" in lowered:
            return "Virtualization deshabilitada (TDM_ENABLE_VIRTUALIZATION=false)."
        if "tdm synthetic planning is disabled" in lowered:
            return "Synthetic deshabilitado (TDM_ENABLE_SYNTHETIC=false)."
        if "disabled" in lowered:
            return "Capacidad TDM deshabilitada por feature flag."
        if "503" in lowered or "service unavailable" in lowered:
            return "Backend TDM no disponible temporalmente (503)."
        return "Operacion TDM fallo."

    def _set_status(self, state: str, hint: str) -> None:
        """Update status badge state and hint text."""
        label_by_state = {
            "idle": "inactivo",
            "running": "en curso",
            "success": "ok",
            "error": "error",
        }
        self.status_label.setProperty("state", state)
        self.status_label.setText(label_by_state.get(state, "inactivo"))
        self.status_hint.setText(hint)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.update()

    def _toggle_raw(self, checked: bool) -> None:
        """Toggle raw JSON visibility."""
        self.raw.setVisible(checked)

    @staticmethod
    def _optional(raw: str) -> str | None:
        """Convert empty strings to None for optional payload fields."""
        value = raw.strip()
        return value or None

    @staticmethod
    def _safe_json(raw: str) -> dict[str, Any]:
        """Parse JSON object safely, defaulting to empty dict."""
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
        return {}

    @staticmethod
    def _safe_int(raw: str) -> int | None:
        """Parse integer safely and return None when invalid."""
        try:
            return int(raw)
        except ValueError:
            return None
