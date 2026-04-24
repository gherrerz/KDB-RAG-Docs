"""Resilience tests for SQLite metadata store lifecycle events."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime

from coderag.core.models import ChunkRecord, DocumentRecord
from coderag.storage.metadata_store import MetadataStore


def test_touch_job_recovers_after_storage_dir_removed(tmp_path) -> None:
    """Ensure DB reconnect works after storage directory is deleted."""
    db_path = tmp_path / "storage" / "metadata.db"
    store = MetadataStore(db_path)

    first = store.touch_job("job-1", "queued", "first")
    assert first.job_id == "job-1"

    shutil.rmtree(db_path.parent)

    second = store.touch_job("job-2", "queued", "second")
    assert second.job_id == "job-2"
    assert db_path.exists()
    assert store.get_job("job-2") is not None


def test_list_documents_returns_lightweight_catalog_entries(tmp_path) -> None:
    """List document catalog rows without exposing full content payloads."""
    db_path = tmp_path / "storage" / "metadata.db"
    store = MetadataStore(db_path)

    store.upsert_document(
        DocumentRecord(
            document_id="doc-1",
            source_id="src-1",
            title="Policy Finance",
            content="secret body",
            path_or_url="sample_data/policy_finance.md",
            content_type="md",
            updated_at=datetime.now(UTC),
            metadata={"origin": "folder"},
        )
    )

    documents = store.list_documents(source_id="src-1")

    assert len(documents) == 1
    assert documents[0].document_id == "doc-1"
    assert documents[0].title == "Policy Finance"
    assert documents[0].path_or_url == "sample_data/policy_finance.md"
    assert not hasattr(documents[0], "content")


def test_find_documents_by_title_and_content_type_is_case_insensitive(
    tmp_path,
) -> None:
    """Match duplicates by title and content_type regardless of case."""
    db_path = tmp_path / "storage" / "metadata.db"
    store = MetadataStore(db_path)

    store.upsert_document(
        DocumentRecord(
            document_id="doc-1",
            source_id="src-1",
            title="Policy Finance",
            content="body-1",
            path_or_url="sample_data/policy_finance.md",
            content_type="MD",
            updated_at=datetime.now(UTC),
            metadata={"origin": "folder"},
        )
    )
    store.upsert_document(
        DocumentRecord(
            document_id="doc-2",
            source_id="src-2",
            title="policy finance",
            content="body-2",
            path_or_url="storage/ingestion_staging/copy/policy_finance.md",
            content_type="md",
            updated_at=datetime.now(UTC),
            metadata={"origin": "folder"},
        )
    )

    duplicates = store.find_documents_by_title_and_content_type(
        title="POLICY FINANCE",
        content_type="md",
    )

    assert [item.document_id for item in duplicates] == ["doc-2", "doc-1"]


def test_delete_document_and_chunks_by_document_id(tmp_path) -> None:
    """Delete one document and its chunks without affecting others."""
    db_path = tmp_path / "storage" / "metadata.db"
    store = MetadataStore(db_path)

    store.upsert_document(
        DocumentRecord(
            document_id="doc-1",
            source_id="src-1",
            title="Engineering",
            content="body-1",
            path_or_url="sample_data/engineering.md",
            content_type="md",
            updated_at=datetime.now(UTC),
            metadata={"origin": "folder"},
        )
    )
    store.upsert_document(
        DocumentRecord(
            document_id="doc-2",
            source_id="src-2",
            title="Policy Finance",
            content="body-2",
            path_or_url="sample_data/policy_finance.md",
            content_type="md",
            updated_at=datetime.now(UTC),
            metadata={"origin": "folder"},
        )
    )
    store.replace_chunks(
        source_id="src-1",
        chunks=[
            ChunkRecord(
                chunk_id="chunk-1",
                document_id="doc-1",
                source_id="src-1",
                section_name="intro",
                text="hello",
                start_ref=0,
                end_ref=5,
                entity_name=None,
                entity_type=None,
                metadata={},
            )
        ],
    )
    store.replace_chunks(
        source_id="src-2",
        chunks=[
            ChunkRecord(
                chunk_id="chunk-2",
                document_id="doc-2",
                source_id="src-2",
                section_name="intro",
                text="world",
                start_ref=0,
                end_ref=5,
                entity_name=None,
                entity_type=None,
                metadata={},
            )
        ],
    )

    deleted_chunks = store.delete_chunks_by_document_id("doc-1")
    deleted_documents = store.delete_document_by_id("doc-1")

    remaining_documents = store.list_documents()
    remaining_chunks = store.list_chunks()

    assert deleted_chunks == 1
    assert deleted_documents == 1
    assert [item.document_id for item in remaining_documents] == ["doc-2"]
    assert [item.chunk_id for item in remaining_chunks] == ["chunk-2"]
