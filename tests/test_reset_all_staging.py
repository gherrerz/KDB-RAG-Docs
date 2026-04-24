"""Tests for destructive filesystem cleanup used by full reset."""

from __future__ import annotations

from pathlib import Path

from coderag.core.settings import SETTINGS
from coderag.core.service import _clear_local_staging_mirror
from coderag.ingestion.index_chroma import ChromaVectorIndex
from coderag.ui import staging


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


def test_reset_cleans_same_staging_root_used_by_ui_staging(tmp_path: Path) -> None:
    """UI staging and reset should point to the same physical data_dir root."""
    original_repo_root = staging.REPO_ROOT
    original_data_dir = SETTINGS.data_dir

    source_dir = tmp_path / "docs"
    source_dir.mkdir(parents=True)
    (source_dir / "doc.md").write_text("hello", encoding="utf-8")

    staging.REPO_ROOT = tmp_path
    SETTINGS.data_dir = tmp_path / "runtime-storage"
    try:
        runtime_path, metadata = staging.stage_folder_source("docs")
        staged_dir = Path(runtime_path)

        deleted_entries, warnings = _clear_local_staging_mirror(
            SETTINGS.data_dir
        )

        assert metadata["staged_path"] == str(staged_dir)
        assert staged_dir.parent == SETTINGS.data_dir / "ingestion_staging"
        assert deleted_entries == 1
        assert warnings == []
        assert staged_dir.exists() is False
        assert (SETTINGS.data_dir / "ingestion_staging").exists()
    finally:
        staging.REPO_ROOT = original_repo_root
        SETTINGS.data_dir = original_data_dir


def test_chroma_clear_all_recreates_persist_dir(tmp_path: Path) -> None:
    """Reset should physically remove and recreate the Chroma persist dir."""
    original_persist_dir = SETTINGS.chroma_persist_dir
    original_use_chroma = SETTINGS.use_chroma

    chroma_dir = tmp_path / "chromadb"
    marker_dir = chroma_dir / "stale"
    marker_dir.mkdir(parents=True)
    marker_file = marker_dir / "marker.txt"
    marker_file.write_text("obsolete", encoding="utf-8")

    SETTINGS.use_chroma = True
    SETTINGS.chroma_persist_dir = chroma_dir

    index = ChromaVectorIndex(size=8, provider="local", model=None)
    try:
        index.clear_all()

        assert chroma_dir.exists()
        assert marker_file.exists() is False
        assert list(chroma_dir.iterdir()) != []
    finally:
        index.close()
        SETTINGS.chroma_persist_dir = original_persist_dir
        SETTINGS.use_chroma = original_use_chroma
