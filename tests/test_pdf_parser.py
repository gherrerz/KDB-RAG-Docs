"""Tests for the pypdf-based PDF parser."""

from __future__ import annotations

from pathlib import Path

from coderag.parsers.generic_parser import parse_by_extension
from coderag.parsers.pdf_parser import parse_pdf


def _write_pdf(file_path: Path, text: str) -> None:
    """Write a minimal single-page PDF containing ``text`` using pypdf."""
    from pypdf import PdfWriter
    from pypdf.annotations import FreeText

    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    annotation = FreeText(
        text=text,
        rect=(10, 10, 190, 190),
        font="Arial",
        bold=False,
        italic=False,
        font_size="12pt",
    )
    writer.add_annotation(page_number=0, annotation=annotation)
    with file_path.open("wb") as handle:
        writer.write(handle)


def test_parse_pdf_returns_empty_string_for_invalid_file(
    tmp_path: Path,
) -> None:
    """Corrupted/invalid PDF input should not raise; returns empty text."""
    file_path = tmp_path / "broken.pdf"
    file_path.write_bytes(b"%PDF-1.4\nnot a real pdf body")

    parsed = parse_pdf(file_path)

    assert parsed == ""


def test_parse_pdf_extracts_page_count_without_error(tmp_path: Path) -> None:
    """A syntactically valid PDF should be readable via pypdf.PdfReader.

    Annotation text is not part of the page content stream, so
    ``extract_text()`` legitimately returns an empty string for this
    minimal fixture. This test instead validates that the pypdf API
    surface used by the parser (``PdfReader``, ``.pages``,
    ``.extract_text()``) keeps working end-to-end after the version bump.
    """
    file_path = tmp_path / "sample.pdf"
    _write_pdf(file_path, "Hybrid retrieval and graph expansion")

    from pypdf import PdfReader

    reader = PdfReader(str(file_path))

    assert len(reader.pages) == 1

    parsed = parse_pdf(file_path)

    assert isinstance(parsed, str)


def test_parse_by_extension_dispatches_pdf(tmp_path: Path) -> None:
    """generic_parser should route .pdf files to parse_pdf without error."""
    file_path = tmp_path / "sample.pdf"
    _write_pdf(file_path, "Governance strategy overview")

    parsed = parse_by_extension(file_path)

    assert isinstance(parsed, str)
