"""Unit tests for the PostgreSQL-backed ingestion artifact store."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import shutil
from typing import Any

from coderag.storage.postgres_ingestion_artifact_store import (
    PostgresIngestionArtifactStore,
)
from coderag.storage.postgres_schema import (
    ingestion_artifact_files_table,
    ingestion_artifacts_table,
)


class _FakeExecuteResult:
    """Minimal execute result object for write statements."""

    def __init__(self, rowcount: int | None = None) -> None:
        """Store optional rowcount for delete or update assertions."""
        self.rowcount = rowcount


class _FakeMappingsResult:
    """Minimal mappings result object for select statements."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        """Store the mapping rows returned by one fake select."""
        self._rows = rows

    def one_or_none(self) -> dict[str, Any] | None:
        """Return the first row or None when the result is empty."""
        return self._rows[0] if self._rows else None

    def all(self) -> list[dict[str, Any]]:
        """Return all mapping rows."""
        return self._rows


class _FakeReadResult:
    """Minimal execute result wrapper for select mappings."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        """Store rows that should be exposed through mappings()."""
        self._rows = rows

    def mappings(self) -> _FakeMappingsResult:
        """Expose the fake rows through the mappings API."""
        return _FakeMappingsResult(self._rows)


class _FakeConnection:
    """Collect executed statements and replay configured results."""

    def __init__(self, results: list[_FakeExecuteResult]) -> None:
        """Store queued execute results for later replay."""
        self._results = list(results)
        self.statements: list[Any] = []

    def execute(self, statement: Any) -> _FakeExecuteResult:
        """Record the statement and return the next queued result."""
        self.statements.append(statement)
        if not self._results:
            return _FakeExecuteResult()
        return self._results.pop(0)


class _FakeSessionFactory:
    """Provide one fake connection through get_connection()."""

    def __init__(self, connection: _FakeConnection) -> None:
        """Retain the connection used by the store under test."""
        self.connection = connection

    @contextmanager
    def get_connection(self) -> Any:
        """Yield the fake connection as a context manager."""
        yield self.connection


def test_create_uploaded_batch_artifact_writes_parent_and_files() -> None:
    """Creating one artifact should write parent and child rows."""
    connection = _FakeConnection([_FakeExecuteResult(), _FakeExecuteResult()])
    store = PostgresIngestionArtifactStore(
        "postgresql://docs:secret@db.local/docs",
        session_factory=_FakeSessionFactory(connection),
    )

    artifact_id = store.create_uploaded_batch_artifact(
        source_type="folder",
        origin_path_or_url="C:/tmp/upload-batch",
        files=[
            {
                "ordinal": 0,
                "original_filename": "notes.md",
                "staged_filename": "notes.md",
                "media_type": "text/markdown",
                "size_bytes": 5,
                "content_hash": "hash-1",
                "payload": b"hello",
            },
            {
                "ordinal": 1,
                "original_filename": "plan.txt",
                "staged_filename": "plan.txt",
                "media_type": "text/plain",
                "size_bytes": 5,
                "content_hash": "hash-2",
                "payload": b"world",
            },
        ],
    )

    assert artifact_id
    assert connection.statements[0].table.name == ingestion_artifacts_table.name
    assert connection.statements[1].table.name == ingestion_artifact_files_table.name


def test_status_updates_target_artifact_parent_table() -> None:
    """Job attachment and lifecycle updates should target the parent table."""
    connection = _FakeConnection([
        _FakeExecuteResult(),
        _FakeExecuteResult(),
        _FakeExecuteResult(),
        _FakeExecuteResult(),
        _FakeExecuteResult(rowcount=2),
        _FakeExecuteResult(rowcount=0),
    ])
    store = PostgresIngestionArtifactStore(
        "postgresql://docs:secret@db.local/docs",
        session_factory=_FakeSessionFactory(connection),
    )

    store.attach_job("artifact-1", "job-1")
    store.mark_processing_started("artifact-1")
    store.mark_processing_completed("artifact-1")
    store.mark_processing_failed("artifact-1", "boom")

    assert [statement.table.name for statement in connection.statements] == [
        ingestion_artifacts_table.name,
        ingestion_artifacts_table.name,
        ingestion_artifacts_table.name,
        ingestion_artifact_files_table.name,
        ingestion_artifacts_table.name,
        ingestion_artifact_files_table.name,
    ]


def test_materialize_uploaded_batch_restores_files_from_artifact_rows() -> None:
    """Materialization should recreate staged filenames from persisted rows."""
    connection = _FakeConnection(
        [
            _FakeReadResult(
                [{"file_manifest": [{"ordinal": 0, "staged_filename": "Doc.md"}]}]
            ),
            _FakeReadResult(
                [
                    {
                        "ordinal": 0,
                        "original_filename": "doc.md",
                        "payload": b"hello",
                    }
                ]
            ),
        ]
    )
    store = PostgresIngestionArtifactStore(
        "postgresql://docs:secret@db.local/docs",
        session_factory=_FakeSessionFactory(connection),
    )

    materialized_dir = Path(store.materialize_uploaded_batch("artifact-1"))
    try:
        assert (materialized_dir / "Doc.md").read_bytes() == b"hello"
    finally:
        shutil.rmtree(materialized_dir, ignore_errors=True)


def test_clear_uploaded_artifacts_deletes_parent_table() -> None:
    """Artifact cleanup should delete from the parent artifact table."""
    connection = _FakeConnection([_FakeExecuteResult(rowcount=3)])
    store = PostgresIngestionArtifactStore(
        "postgresql://docs:secret@db.local/docs",
        session_factory=_FakeSessionFactory(connection),
    )

    deleted = store.clear_uploaded_artifacts()

    assert deleted == 3
    assert connection.statements[0].table.name == ingestion_artifacts_table.name


def test_purge_expired_uploaded_artifacts_targets_expires_at_filter() -> None:
    """TTL purge should delete only parent rows whose expiration already passed."""
    connection = _FakeConnection([_FakeExecuteResult(rowcount=2)])
    store = PostgresIngestionArtifactStore(
        "postgresql://docs:secret@db.local/docs",
        session_factory=_FakeSessionFactory(connection),
    )

    deleted = store.purge_expired_uploaded_artifacts()

    assert deleted == 2
    statement = connection.statements[0]
    assert statement.table.name == ingestion_artifacts_table.name
    assert "expires_at" in str(statement.whereclause)