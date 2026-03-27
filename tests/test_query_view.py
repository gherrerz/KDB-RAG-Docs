"""UI tests for query mode payload wiring in QueryView."""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from coderag.ui.query_view import QueryView


def _ensure_app() -> QApplication:
    """Return a QApplication instance for widget tests."""
    app = QApplication.instance()
    if app is not None:
        return app
    return QApplication([])


def test_query_view_sends_include_llm_answer_true_by_default() -> None:
    """Send include_llm_answer=true when checkbox remains checked."""
    _ensure_app()
    captured_payload: dict[str, Any] = {}

    def _on_query(payload: dict[str, Any]) -> dict[str, Any]:
        captured_payload.update(payload)
        return {
            "answer": "ok",
            "diagnostics": {},
            "citations": [],
            "graph_paths": [],
        }

    view = QueryView(_on_query)
    view.question.setText("What is ISO 27001?")
    view.source_id.setText("")
    view.hops.setText("2")

    view._run_query()

    assert captured_payload["include_llm_answer"] is True
    assert captured_payload["hops"] == 2


def test_query_view_sends_include_llm_answer_false_when_unchecked() -> None:
    """Send include_llm_answer=false when checkbox is disabled by user."""
    _ensure_app()
    captured_payload: dict[str, Any] = {}

    def _on_query(payload: dict[str, Any]) -> dict[str, Any]:
        captured_payload.update(payload)
        return {
            "answer": "ok",
            "diagnostics": {},
            "citations": [],
            "graph_paths": [],
        }

    view = QueryView(_on_query)
    view.question.setText("What is ISO 27001?")
    view.hops.setText("2")
    view.include_llm_answer.setChecked(False)

    view._run_query()

    assert captured_payload["include_llm_answer"] is False
    assert captured_payload["hops"] == 2
