"""Evidence table widget for displaying citations and graph paths."""

from __future__ import annotations

from typing import List

from PySide6.QtWidgets import (
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
            ["Chunk", "Score", "Document", "Section", "Snippet"]
        )

        self.graph_paths = QTextEdit()
        self.graph_paths.setReadOnly(True)
        self.graph_paths.setPlaceholderText("Graph paths will appear here")

        layout.addWidget(self.table)
        layout.addWidget(self.graph_paths)

    def update_evidence(
        self,
        citations: List[dict],
        paths: List[dict],
    ) -> None:
        """Refresh evidence table and graph section."""
        self.table.setRowCount(len(citations))
        for row, item in enumerate(citations):
            values = [
                item.get("chunk_id", ""),
                f"{item.get('score', 0.0):.4f}",
                item.get("path_or_url", ""),
                item.get("section_name", ""),
                item.get("snippet", ""),
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))

        lines = []
        for path in paths:
            nodes = " -> ".join(path.get("nodes", []))
            rels = " | ".join(path.get("relationships", []))
            lines.append(f"{nodes}\n  relations: {rels}")
        self.graph_paths.setPlainText("\n\n".join(lines))
