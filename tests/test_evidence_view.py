"""UI tests for evidence table rendering and detail panel behavior."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from coderag.ui.evidence_view import EvidenceView


def _ensure_app() -> QApplication:
    """Return a QApplication instance for widget tests."""
    app = QApplication.instance()
    if app is not None:
        return app
    return QApplication([])


def _build_view() -> EvidenceView:
    """Create an EvidenceView widget ready for tests."""
    _ensure_app()
    return EvidenceView()


def test_evidence_view_sorts_by_score_descending() -> None:
    """Keep highest-score citation at first row after update."""
    view = _build_view()
    citations = [
        {
            "chunk_id": "c-low",
            "score": 0.12,
            "path_or_url": "doc-low.md",
            "section_name": "A",
            "snippet": "low score snippet",
        },
        {
            "chunk_id": "c-high",
            "score": 0.98,
            "path_or_url": "doc-high.md",
            "section_name": "B",
            "snippet": "high score snippet",
        },
    ]

    view.update_evidence(citations, paths=[])

    assert view.table.rowCount() == 2
    assert view.table.item(0, 0).text() == "c-high"
    assert view.table.item(0, 1).text() == "0.9800"


def test_evidence_view_renders_selected_row_detail() -> None:
    """Show expanded evidence details when a row is selected."""
    view = _build_view()
    citations = [
        {
            "chunk_id": "chunk-7",
            "score": 0.61,
            "path_or_url": "policy_finance.md",
            "section_name": "Controls",
            "snippet": "ISO 27001 controls mapping paragraph.",
        }
    ]

    view.update_evidence(citations, paths=[])
    view.table.selectRow(0)
    view._render_selected_detail()

    detail = view.detail.toPlainText()
    assert "Chunk ID: chunk-7" in detail
    assert "Score: 0.6100" in detail
    assert "policy_finance.md" in detail
    assert "ISO 27001 controls mapping paragraph." in detail


def test_evidence_view_truncates_snippet_and_keeps_tooltip() -> None:
    """Keep table compact while preserving full snippet in tooltip/detail."""
    view = _build_view()
    long_snippet = "A" * 240
    citations = [
        {
            "chunk_id": "chunk-long",
            "score": 0.42,
            "path_or_url": "engineering.md",
            "section_name": "Appendix",
            "snippet": long_snippet,
        }
    ]

    view.update_evidence(citations, paths=[])

    table_text = view.table.item(0, 4).text()
    table_tooltip = view.table.item(0, 4).toolTip()

    assert table_text.endswith("...")
    assert len(table_text) == 180
    assert table_tooltip == long_snippet


def test_evidence_view_renders_graph_paths_text() -> None:
    """Render graph paths in human-readable multiline format."""
    view = _build_view()
    paths = [
        {
            "nodes": ["Policy FIN-001", "Control A.5", "Procedure P-12"],
            "relationships": ["maps_to", "implemented_by"],
        }
    ]

    view.update_evidence(citations=[], paths=paths)

    text = view.graph_paths.toPlainText()
    assert "Policy FIN-001 -> Control A.5 -> Procedure P-12" in text
    assert "relations: maps_to | implemented_by" in text
