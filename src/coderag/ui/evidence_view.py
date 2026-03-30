"""Evidence table widget for displaying citations and graph paths."""

from __future__ import annotations

from html import escape
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView
from PySide6.QtWidgets import (
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class EvidenceView(QWidget):
    """Widget that renders citation rows and graph traces."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Chunk", "Score", "Documento", "Seccion", "Fragmento"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.itemSelectionChanged.connect(self._render_selected_detail)

        self.detail_title = QLabel("Detalle de evidencia seleccionada")
        self.detail_title.setProperty("role", "hint")
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMinimumHeight(150)
        self.detail.setPlaceholderText(
            "Selecciona una fila de citacion para ver metadatos y fragmento completo."
        )
        self.detail.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)

        self.graph_paths = QTextEdit()
        self.graph_paths.setReadOnly(True)
        self.graph_paths.setPlaceholderText("Las rutas del grafo apareceran aqui")

        detail_panel = QWidget()
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(6)
        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail)

        self.content_splitter = QSplitter(Qt.Orientation.Vertical)
        self.content_splitter.addWidget(self.table)
        self.content_splitter.addWidget(detail_panel)
        self.content_splitter.addWidget(self.graph_paths)
        self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.setStretchFactor(0, 3)
        self.content_splitter.setStretchFactor(1, 2)
        self.content_splitter.setStretchFactor(2, 2)
        self.content_splitter.setSizes([220, 160, 160])

        layout.addWidget(self.content_splitter)

    def update_evidence(
        self,
        citations: List[dict],
        paths: List[dict],
    ) -> None:
        """Refresh evidence table and graph section."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(citations))
        for row, item in enumerate(citations):
            snippet = str(item.get("snippet", ""))
            short_snippet = self._truncate(snippet, limit=180)
            values = [
                item.get("chunk_id", ""),
                f"{item.get('score', 0.0):.4f}",
                item.get("path_or_url", ""),
                item.get("section_name", ""),
                short_snippet,
            ]
            for col, value in enumerate(values):
                table_item = QTableWidgetItem(str(value))
                table_item.setFlags(
                    Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                )
                if col == 4:
                    table_item.setToolTip(snippet)
                self.table.setItem(row, col, table_item)

        self.table.setSortingEnabled(True)
        self.table.sortItems(1, Qt.SortOrder.DescendingOrder)
        if self.table.rowCount() > 0:
            self.table.selectRow(0)
        else:
            self._set_empty_detail()

        lines = []
        for path in paths:
            nodes = " -> ".join(path.get("nodes", []))
            rels = " | ".join(path.get("relationships", []))
            lines.append(f"{nodes}\n  relations: {rels}")
        self.graph_paths.setPlainText("\n\n".join(lines))

    def _render_selected_detail(self) -> None:
        """Render focused detail for the currently selected evidence row."""
        selected_items = self.table.selectedItems()
        if not selected_items:
            self._set_empty_detail()
            return

        row = selected_items[0].row()
        chunk_id = self._item_text(row, 0)
        score = self._item_text(row, 1)
        document = self._item_text(row, 2)
        section = self._item_text(row, 3)
        snippet = self._item_text(row, 4)
        snippet_tooltip = self.table.item(row, 4).toolTip() if self.table.item(row, 4) else ""
        full_snippet = snippet_tooltip or snippet

        self.detail.setHtml(
            """
            <div>
              <p><b>Chunk ID:</b> {chunk_id}</p>
              <p><b>Score:</b> {score}</p>
              <p><b>Documento:</b> {document}</p>
              <p><b>Seccion:</b> {section}</p>
              <p style="margin-top:10px;"><b>Fragmento completo</b></p>
              <pre style="white-space: pre-wrap; margin: 4px 0 0 0;">{snippet}</pre>
            </div>
            """.format(
                chunk_id=escape(chunk_id or "-"),
                score=escape(score or "-"),
                document=escape(document or "-"),
                section=escape(section or "-"),
                snippet=escape(full_snippet or "-"),
            )
        )

    def _set_empty_detail(self) -> None:
        """Show a helpful message when no citation row is selected."""
        self.detail.setPlainText(
            "Selecciona una fila de citacion para inspeccionar detalles completos."
        )

    def _item_text(self, row: int, col: int) -> str:
        """Return table item text safely."""
        item = self.table.item(row, col)
        return item.text() if item is not None else ""

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        """Trim long snippets for compact table rendering."""
        if len(text) <= limit:
            return text
        return f"{text[: limit - 3]}..."
