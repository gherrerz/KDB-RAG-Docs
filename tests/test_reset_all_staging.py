"""Tests for destructive filesystem cleanup used by full reset."""

from __future__ import annotations

from pathlib import Path

from coderag.core.settings import SETTINGS
from coderag.core.models import DocumentCatalogEntry
from coderag.core.service import _clear_local_staging_mirror
from coderag.core import service as service_module
from coderag.ingestion.index_chroma import ChromaVectorIndex
from coderag.core.runtime import RUNTIME


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


def test_reset_cleans_legacy_staging_root(tmp_path: Path) -> None:
    """Reset cleanup should keep removing legacy staged folder mirrors."""
    data_dir = tmp_path / "runtime-storage"
    staged_dir = data_dir / "ingestion_staging" / "docs_legacy"
    staged_dir.mkdir(parents=True)
    (staged_dir / "doc.md").write_text("hello", encoding="utf-8")

    deleted_entries, warnings = _clear_local_staging_mirror(data_dir)

    assert deleted_entries == 1
    assert warnings == []
    assert staged_dir.exists() is False
    assert (data_dir / "ingestion_staging").exists()


def test_delete_staged_document_copy_accepts_logical_staging_path(
    tmp_path: Path,
) -> None:
    """Logical staging paths should still map back to the managed mirror."""
    data_dir = tmp_path / "storage"
    staged_file = data_dir / "ingestion_staging" / "old-copy" / "atlas.md"
    staged_file.parent.mkdir(parents=True, exist_ok=True)
    staged_file.write_text("hello", encoding="utf-8")

    deleted, warning = service_module._delete_staged_document_copy(
        data_dir,
        "old-copy/atlas.md",
    )

    assert deleted is True
    assert warning is None
    assert staged_file.exists() is False


def test_reset_all_skips_legacy_staging_cleanup_without_staged_docs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Reset should not touch ingestion_staging when no legacy docs exist."""
    original_store = RUNTIME.store
    original_data_dir = SETTINGS.data_dir
    staging_dir = tmp_path / "storage" / "ingestion_staging"

    class _StoreStub:
        def list_documents(self, source_id=None, tags=None):
            return [
                DocumentCatalogEntry(
                    document_id="doc-1",
                    source_id="src-1",
                    title="Engineering",
                    path_or_url="sample_data/engineering.md",
                    content_type="md",
                    updated_at=service_module.datetime.now(service_module.UTC),
                    tags=[],
                )
            ]

        def clear_all_data(self):
            return {
                "deleted_documents": 0,
                "deleted_chunks": 0,
                "deleted_graph_edges": 0,
                "deleted_jobs": 0,
            }

        def bump_index_version(self):
            return 1

    monkeypatch.setattr(service_module.RUNTIME, "ingestion_artifact_store", type("_Artifacts", (), {"clear_uploaded_artifacts": lambda self: 0})())
    monkeypatch.setattr(service_module.SERVICE, "store", _StoreStub())
    monkeypatch.setattr(service_module.SERVICE.vector_index, "clear_all", lambda: None)
    monkeypatch.setattr(service_module.SERVICE.graph_store, "clear_all_edges", lambda: 0)
    monkeypatch.setattr(service_module.SERVICE, "rebuild_indexes", lambda source_id=None: None)
    monkeypatch.setattr(service_module.SERVICE, "is_graph_enabled", lambda: False)
    monkeypatch.setattr(service_module.SETTINGS, "data_dir", tmp_path / "storage")

    try:
        response = service_module.SERVICE.reset_all()
    finally:
        RUNTIME.store = original_store
        SETTINGS.data_dir = original_data_dir

    assert response.status == "completed"
    assert staging_dir.exists() is False


def test_chroma_clear_all_rejects_embedded_mode(tmp_path: Path) -> None:
    """Embedded Chroma reset should fail explicitly in the final runtime."""
    original_chroma_mode = SETTINGS.chroma_mode
    original_persist_dir = SETTINGS.chroma_persist_dir
    original_use_chroma = SETTINGS.use_chroma

    chroma_dir = tmp_path / "chromadb"
    marker_dir = chroma_dir / "stale"
    marker_dir.mkdir(parents=True)
    marker_file = marker_dir / "marker.txt"
    marker_file.write_text("obsolete", encoding="utf-8")

    SETTINGS.use_chroma = True
    SETTINGS.chroma_mode = "embedded"
    SETTINGS.chroma_persist_dir = chroma_dir

    index = ChromaVectorIndex(size=8, provider="local", model=None)
    try:
        try:
            index.clear_all()
        except RuntimeError as exc:
            assert "no longer supported" in str(exc)
        else:
            raise AssertionError("Expected embedded clear_all to be rejected")

        assert marker_file.exists()
    finally:
        index.close()
        SETTINGS.chroma_mode = original_chroma_mode
        SETTINGS.chroma_persist_dir = original_persist_dir
        SETTINGS.use_chroma = original_use_chroma
