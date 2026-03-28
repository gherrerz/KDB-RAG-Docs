"""Tests for robust folder diagnostics during document loading."""

from __future__ import annotations

from pathlib import Path

from coderag.core.models import SourceConfig
from coderag.ingestion.document_loader import load_documents


def test_load_documents_reports_path_not_found_with_suggestions(
    tmp_path: Path,
) -> None:
    """Return path-not-found diagnostics and nearby folder suggestions."""
    expected = tmp_path / "Planificacion Estrategica"
    suggested = tmp_path / "Planificacion Estrategica 2026"
    suggested.mkdir(parents=True, exist_ok=True)

    source = SourceConfig(
        source_type="folder",
        local_path=str(expected),
    )
    docs, stats = load_documents(source)

    assert docs == []
    assert stats.get("failure_reason") == "path_not_found"
    assert stats.get("path_exists") is False
    suggestions = stats.get("suggested_paths", [])
    assert isinstance(suggestions, list)
    assert any(str(suggested) == str(item) for item in suggestions)


def test_load_documents_reports_no_supported_documents(tmp_path: Path) -> None:
    """Return explicit diagnostics when folder has no supported extensions."""
    root = tmp_path / "source"
    root.mkdir(parents=True, exist_ok=True)
    (root / "table.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (root / "slides.ppt").write_text("legacy", encoding="utf-8")

    source = SourceConfig(
        source_type="folder",
        local_path=str(root),
    )
    docs, stats = load_documents(source)

    assert docs == []
    assert stats.get("failure_reason") == "no_supported_documents"
    assert stats.get("path_exists") is True
    assert stats.get("path_is_dir") is True
    assert int(stats.get("total_files_seen", 0)) == 2
    assert int(stats.get("discovered_files", 0)) == 0
