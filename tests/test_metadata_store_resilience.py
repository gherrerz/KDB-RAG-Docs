"""Resilience and contract tests for the Postgres-backed runtime store."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from coderag.core.models import ChunkRecord, DocumentRecord
from coderag.core.settings import SETTINGS
from coderag.storage.hybrid_metadata_store import HybridMetadataStore
from coderag.storage.postgres_session import resolve_postgres_dsn
from coderag.storage.postgres_startup import ensure_postgres_schema_ready


def _build_store() -> HybridMetadataStore:
    """Build the runtime metadata store backed by PostgreSQL."""
    ensure_postgres_schema_ready(SETTINGS, force=True)
    postgres_dsn = resolve_postgres_dsn(SETTINGS)
    if not postgres_dsn:
        pytest.skip("Postgres DSN is required for runtime store tests.")
    return HybridMetadataStore(postgres_dsn=postgres_dsn)


def test_touch_job_roundtrip_updates_status() -> None:
    """Persist one job and confirm status updates are readable."""
    store = _build_store()
    job_id = f"job-{uuid4().hex}"

    first = store.touch_job(job_id, "queued", "first")
    second = store.touch_job(job_id, "running", "second")
    loaded = store.get_job(job_id)

    assert first.job_id == job_id
    assert second.job_id == job_id
    assert loaded is not None
    assert loaded.status == "running"


def test_list_documents_returns_lightweight_catalog_entries() -> None:
    """List document catalog rows without exposing full content payloads."""
    store = _build_store()
    source_id = f"src-{uuid4().hex}"
    document_id = f"doc-{uuid4().hex}"

    store.upsert_document(
        DocumentRecord(
            document_id=document_id,
            source_id=source_id,
            title="Policy Finance",
            content="secret body",
            path_or_url=f"sample_data/{document_id}.md",
            content_type="md",
            updated_at=datetime.now(UTC),
            metadata={"origin": "folder"},
        )
    )

    documents = store.list_documents(source_id=source_id)

    assert len(documents) == 1
    assert documents[0].document_id == document_id
    assert documents[0].title == "Policy Finance"
    assert documents[0].path_or_url == f"sample_data/{document_id}.md"
    assert not hasattr(documents[0], "content")


def test_find_documents_by_title_and_content_type_is_case_insensitive() -> None:
    """Match duplicates by title and content_type regardless of case."""
    store = _build_store()
    title_token = uuid4().hex
    title = f"Policy Finance {title_token}"
    source_one = f"src-{uuid4().hex}"
    source_two = f"src-{uuid4().hex}"
    doc_one = f"doc-{uuid4().hex}"
    doc_two = f"doc-{uuid4().hex}"

    store.upsert_document(
        DocumentRecord(
            document_id=doc_one,
            source_id=source_one,
            title=title,
            content="body-1",
            path_or_url=f"sample_data/{doc_one}.md",
            content_type="MD",
            updated_at=datetime.now(UTC),
            metadata={"origin": "folder"},
        )
    )
    store.upsert_document(
        DocumentRecord(
            document_id=doc_two,
            source_id=source_two,
            title=title.lower(),
            content="body-2",
            path_or_url=f"storage/ingestion_staging/{doc_two}.md",
            content_type="md",
            updated_at=datetime.now(UTC),
            metadata={"origin": "folder"},
        )
    )

    duplicates = store.find_documents_by_title_and_content_type(
        title=title.upper(),
        content_type="md",
    )

    duplicate_ids = {item.document_id for item in duplicates}
    assert duplicate_ids == {doc_one, doc_two}


def test_delete_document_and_chunks_by_document_id() -> None:
    """Delete one document and its chunks without affecting others."""
    store = _build_store()
    source_one = f"src-{uuid4().hex}"
    source_two = f"src-{uuid4().hex}"
    doc_one = f"doc-{uuid4().hex}"
    doc_two = f"doc-{uuid4().hex}"
    chunk_one = f"chunk-{uuid4().hex}"
    chunk_two = f"chunk-{uuid4().hex}"

    store.upsert_document(
        DocumentRecord(
            document_id=doc_one,
            source_id=source_one,
            title="Engineering",
            content="body-1",
            path_or_url=f"sample_data/{doc_one}.md",
            content_type="md",
            updated_at=datetime.now(UTC),
            metadata={"origin": "folder"},
        )
    )
    store.upsert_document(
        DocumentRecord(
            document_id=doc_two,
            source_id=source_two,
            title="Policy Finance",
            content="body-2",
            path_or_url=f"sample_data/{doc_two}.md",
            content_type="md",
            updated_at=datetime.now(UTC),
            metadata={"origin": "folder"},
        )
    )
    store.replace_chunks(
        source_id=source_one,
        chunks=[
            ChunkRecord(
                chunk_id=chunk_one,
                document_id=doc_one,
                source_id=source_one,
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
        source_id=source_two,
        chunks=[
            ChunkRecord(
                chunk_id=chunk_two,
                document_id=doc_two,
                source_id=source_two,
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

    deleted_chunks = store.delete_chunks_by_document_id(doc_one)
    deleted_documents = store.delete_document_by_id(doc_one)

    remaining_documents = store.list_documents(source_id=source_two)
    remaining_chunks = store.list_chunks(source_id=source_two)

    assert deleted_chunks == 1
    assert deleted_documents == 1
    assert [item.document_id for item in remaining_documents] == [doc_two]
    assert [item.chunk_id for item in remaining_chunks] == [chunk_two]
