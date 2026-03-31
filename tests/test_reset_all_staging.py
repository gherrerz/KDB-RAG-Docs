"""Tests for staging mirror cleanup used by full reset."""

from __future__ import annotations

from coderag.core.service import _clear_local_staging_mirror


def test_clear_local_staging_mirror_removes_files_and_dirs(tmp_path) -> None:
    """Ensure staged folders/files are removed and root directory is kept."""
    data_dir = tmp_path / "storage"
    staging_dir = data_dir / "ingestion_staging"
    source_dir = staging_dir / "sample_source_1"
    source_dir.mkdir(parents=True)
    (source_dir / "doc.md").write_text("hello", encoding="utf-8")
    (staging_dir / "notes.txt").write_text("temp", encoding="utf-8")

    deleted_entries, warnings = _clear_local_staging_mirror(data_dir)

    assert deleted_entries == 2
    assert warnings == []
    assert staging_dir.exists()
    assert list(staging_dir.iterdir()) == []


def test_clear_local_staging_mirror_creates_dir_when_missing(tmp_path) -> None:
    """Create ingestion staging root when it does not exist yet."""
    data_dir = tmp_path / "storage"

    deleted_entries, warnings = _clear_local_staging_mirror(data_dir)

    assert deleted_entries == 0
    assert warnings == []
    assert (data_dir / "ingestion_staging").exists()
