"""Query panel for asking grounded questions."""

from __future__ import annotations

import json
from typing import Callable

from PySide6.QtWidgets import (
    QCheckBox,
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

from coderag.ui.evidence_view import EvidenceView


class QueryView(QWidget):
    """Widget for querying backend and presenting evidence."""

    def __init__(self, on_query: Callable[[dict], dict]) -> None:
        super().__init__()
        self._on_query = on_query

        layout = QVBoxLayout(self)
        group = QGroupBox("Ask Questions")
        form = QFormLayout(group)

        self.question = QLineEdit()
        self.source_id = QLineEdit()
        self.hops = QLineEdit("2")
        self.include_llm_answer = QCheckBox("Include LLM answer")
        self.include_llm_answer.setChecked(True)

        form.addRow("Question", self.question)
        form.addRow("Source ID (optional)", self.source_id)
        form.addRow("Graph Hops", self.hops)
        form.addRow("Response Mode", self.include_llm_answer)

        actions = QHBoxLayout()
        self.query_button = QPushButton("Query")
        self.query_button.clicked.connect(self._run_query)
        actions.addWidget(self.query_button)
        actions.addWidget(QLabel("Hybrid retrieval + graph expansion"))

        self.answer = QTextEdit()
        self.answer.setReadOnly(True)
        self.evidence = EvidenceView()

        layout.addWidget(group)
        layout.addLayout(actions)
        layout.addWidget(self.answer)
        layout.addWidget(self.evidence)

    def _run_query(self) -> None:
        payload = {
            "question": self.question.text().strip(),
            "source_id": self.source_id.text().strip() or None,
            "hops": self._safe_int(self.hops.text().strip()),
            "include_llm_answer": self.include_llm_answer.isChecked(),
        }
        result = self._on_query(payload)
        if "answer" in result:
            pretty = {
                "answer": result.get("answer"),
                "diagnostics": result.get("diagnostics", {}),
            }
            self.answer.setPlainText(
                json.dumps(pretty, indent=2, ensure_ascii=False)
            )
            self.evidence.update_evidence(
                result.get("citations", []),
                result.get("graph_paths", []),
            )
        else:
            self.answer.setPlainText(json.dumps(result, indent=2))

    @staticmethod
    def _safe_int(raw: str) -> int | None:
        try:
            return int(raw)
        except ValueError:
            return None
