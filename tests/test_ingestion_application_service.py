"""Unit tests for ingestion helper methods extracted from service facade."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import pytest

import coderag.core.ingestion_service as ingestion_module
from coderag.core.models import ChunkRecord, DocumentRecord
from coderag.core.ingestion_service import IngestionApplicationService


class _StoreStub:
    """Minimal store collaborator used by ingestion helper unit tests."""

    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []
        self.touches: list[tuple[str, str, str]] = []

    def append_job_event(
        self,
        *,
        job_id: str,
        ordinal: int,
        name: str,
        status: str,
        elapsed_ms: float,
        details: dict[str, object],
    ) -> None:
        self.events.append(
            {
                "job_id": job_id,
                "ordinal": ordinal,
                "name": name,
                "status": status,
                "elapsed_ms": elapsed_ms,
                "details": details,
            }
        )

    def touch_job(self, job_id: str, status: str, message: str) -> None:
        self.touches.append((job_id, status, message))

    def get_index_version(self) -> int:
        return 7


class _VectorIndexStub:
    """Minimal vector index collaborator for constructor compatibility."""

    def __init__(self) -> None:
        self.rebuild_calls: list[int] = []

    def rebuild(self, chunks) -> None:  # type: ignore[no-untyped-def]
        self.rebuild_calls.append(len(chunks))

    def clear_all(self) -> None:
        return None


class _GraphStoreStub:
    """Minimal graph collaborator for constructor compatibility."""

    def replace_edges(self, source_id, edges):  # type: ignore[no-untyped-def]
        return {"edges_written": len(list(edges))}

    def clear_all_edges(self) -> int:
        return 0


class _ArtifactStoreStub:
    """Minimal artifact collaborator for constructor compatibility."""

    def clear_uploaded_artifacts(self) -> None:
        return None


def _build_service() -> tuple[IngestionApplicationService, _StoreStub]:
    """Create one isolated ingestion service wired with lightweight stubs."""
    store = _StoreStub()
    service = IngestionApplicationService(
        store=store,  # type: ignore[arg-type]
        vector_index=_VectorIndexStub(),  # type: ignore[arg-type]
        graph_store=_GraphStoreStub(),  # type: ignore[arg-type]
        ingestion_artifact_store=_ArtifactStoreStub(),  # type: ignore[arg-type]
        data_dir=Path("."),
        rebuild_indexes=lambda: None,
        is_graph_enabled=lambda: True,
        delete_persisted_documents=lambda _docs, _skip: {},
        ingest_handler=lambda _request, _progress, _job_id: {},
        is_legacy_staged_path=lambda _data_dir, _path: False,
        clear_local_staging_mirror=lambda _data_dir: (0, []),
    )
    return service, store


def test_append_ingest_step_persists_event_and_running_status() -> None:
    """Step append should persist timeline event and running transition."""
    service, store = _build_service()
    steps: list[dict[str, object]] = []
    progress_events: list[dict[str, object]] = []

    step_counter = service.append_ingest_step(
        job_id="job-1",
        step_counter=0,
        started_at=perf_counter() - 0.05,
        name="load_documents",
        details={"files": 12},
        steps=steps,
        format_elapsed_hhmmss=lambda _ms: "00:00:00",
        progress_callback=progress_events.append,
        progress_pct=30.25,
    )

    assert step_counter == 1
    assert len(steps) == 1
    assert steps[0]["name"] == "load_documents"
    assert steps[0]["progress_pct"] == 30.25
    assert len(store.events) == 1
    assert store.events[0]["name"] == "load_documents"
    assert store.events[0]["details"]["progress_pct"] == 30.25
    assert store.touches[-1] == ("job-1", "running", "30% | load_documents")
    assert progress_events[-1]["status"] == "running"


def test_append_ingest_step_marks_failed_and_emits_failed_status() -> None:
    """Failed step should mark failed job state and failed callback status."""
    service, store = _build_service()
    steps: list[dict[str, object]] = []
    progress_events: list[dict[str, object]] = []

    service.append_ingest_step(
        job_id="job-2",
        step_counter=0,
        started_at=perf_counter() - 0.05,
        name="ingestion_failed",
        details={"reason": "boom"},
        steps=steps,
        format_elapsed_hhmmss=lambda _ms: "00:00:00",
        progress_callback=progress_events.append,
        status="failed",
        progress_pct=100.0,
    )

    assert store.touches[-1] == ("job-2", "failed", "FAILED | ingestion_failed")
    assert progress_events[-1]["status"] == "failed"


def test_append_ingest_step_sets_completed_status_for_final_step() -> None:
    """Final step should emit completed status without running transition."""
    service, store = _build_service()
    steps: list[dict[str, object]] = []
    progress_events: list[dict[str, object]] = []

    service.append_ingest_step(
        job_id="job-3",
        step_counter=0,
        started_at=perf_counter() - 0.05,
        name="ingestion_completed",
        details={"elapsed_hhmmss": "00:00:03"},
        steps=steps,
        format_elapsed_hhmmss=lambda _ms: "00:00:03",
        progress_callback=progress_events.append,
        progress_pct=100.0,
    )

    assert store.touches == []
    assert progress_events[-1]["status"] == "completed"


def test_build_loader_progress_step_maps_percentage() -> None:
    """Loader progress helper should map processed files to expected band."""
    service, _store = _build_service()

    name, details, progress_pct = service.build_loader_progress_step(
        event="loader_progress",
        payload={"total_files": 20, "processed_files": 5},
    )

    assert name == "loader_progress"
    assert details["processed_files"] == 5
    assert progress_pct == 15.0


def test_build_loader_progress_step_defaults_when_totals_missing() -> None:
    """Loader progress should fallback to baseline when totals are absent."""
    service, _store = _build_service()

    _name, _details, progress_pct = service.build_loader_progress_step(
        event="loader_progress",
        payload={"processed_files": 1},
    )

    assert progress_pct == 10.0


def test_build_failed_ingest_message_path_not_found_with_suggestions() -> None:
    """Path-not-found message should include up to three nearby suggestions."""
    service, _store = _build_service()

    message = service.build_failed_ingest_message(
        load_stats={
            "failure_reason": "path_not_found",
            "source_path": "missing-folder",
            "suggested_paths": ["a", "b", "c", "d"],
        },
        local_path="missing-folder",
    )

    assert message == "Source path does not exist: 'missing-folder'. Nearby folders: a; b; c."


def test_build_failed_ingest_message_includes_scan_warning() -> None:
    """Generic no-docs message should append first scan warning example."""
    service, _store = _build_service()

    message = service.build_failed_ingest_message(
        load_stats={
            "failure_reason": "no_supported_documents",
            "source_path": "sample_data",
            "total_files_seen": 3,
            "scan_error_examples": ["permission denied"],
        },
        local_path="sample_data",
    )

    assert "No supported documents found in source path 'sample_data'." in message
    assert "Files scanned: 3." in message
    assert message.endswith("Scan warning: permission denied")


def test_build_failed_ingest_result_preserves_contract_shape() -> None:
    """Failed payload helper should keep the external API response shape."""
    service, _store = _build_service()
    steps = [{"name": "ingestion_failed", "status": "failed"}]

    result = service.build_failed_ingest_result(
        job_id="job-9",
        failure_message="boom",
        steps=steps,
    )

    assert result == {
        "job_id": "job-9",
        "status": "failed",
        "message": "boom",
        "steps": steps,
        "progress_pct": 100.0,
    }


def test_persist_chunk_graph_materialization_skips_store_graph_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Graph edge persistence must bypass RuntimeStore during decommission."""

    class _StoreForPersist:
        def __init__(self) -> None:
            self.documents_calls: list[int] = []
            self.chunk_calls: list[tuple[str, int]] = []

        def upsert_documents(self, docs: list[DocumentRecord]) -> int:
            self.documents_calls.append(len(docs))
            return len(docs)

        def replace_chunks(self, source_id: str, chunks: list[ChunkRecord]) -> None:
            self.chunk_calls.append((source_id, len(chunks)))

    class _GraphStoreForPersist:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def replace_edges(self, source_id: str, edges: object) -> dict[str, int]:
            edge_list = list(edges)
            self.calls.append((source_id, len(edge_list)))
            return {"edges_written": len(edge_list)}

        def clear_all_edges(self) -> int:
            return 0

    store = _StoreForPersist()
    graph_store = _GraphStoreForPersist()
    service = IngestionApplicationService(
        store=store,  # type: ignore[arg-type]
        vector_index=_VectorIndexStub(),  # type: ignore[arg-type]
        graph_store=graph_store,  # type: ignore[arg-type]
        ingestion_artifact_store=_ArtifactStoreStub(),  # type: ignore[arg-type]
        data_dir=Path("."),
        rebuild_indexes=lambda: None,
        is_graph_enabled=lambda: True,
        delete_persisted_documents=lambda _docs, _skip: {},
        ingest_handler=lambda _request, _progress, _job_id: {},
        is_legacy_staged_path=lambda _data_dir, _path: False,
        clear_local_staging_mirror=lambda _data_dir: (0, []),
    )

    doc = DocumentRecord(
        document_id="doc-1",
        source_id="source-1",
        title="T",
        content="body",
        path_or_url="sample_data/doc.md",
        content_type="md",
        updated_at=datetime.now(UTC),
    )
    chunk = ChunkRecord(
        chunk_id="chunk-1",
        document_id="doc-1",
        source_id="source-1",
        section_name="s",
        text="body",
        start_ref=0,
        end_ref=4,
    )
    generated_edges = [
        ("edge-1", "node-a", "RELATES_TO", "node-b", "source-1")
    ]
    monkeypatch.setattr(
        ingestion_module,
        "build_graph_edges",
        lambda source_id, chunks: generated_edges,
    )

    result = service.persist_chunk_graph_materialization(
        source_id="source-1",
        documents=[doc],
        chunks=[chunk],
    )

    assert result["edges"] == generated_edges
    assert store.documents_calls == [1]
    assert store.chunk_calls == [("source-1", 1)]
    assert graph_store.calls == [("source-1", 1)]