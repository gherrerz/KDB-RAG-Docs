"""Integration-style tests for ingestion and query."""

from __future__ import annotations

import hashlib
from pathlib import Path

from coderag.core.runtime import RUNTIME
from coderag.core.models import IngestionRequest, QueryRequest, SourceConfig
from coderag.core.service import RagApplicationService
from coderag.core.settings import SETTINGS
from coderag.ingestion import index_chroma
from coderag.storage.metadata_store import MetadataStore


def _looks_like_hhmmss(value: object) -> bool:
    """Validate expected HH:MM:SS format used in public time payloads."""
    if not isinstance(value, str):
        return False
    parts = value.split(":")
    if len(parts) != 3:
        return False
    return all(part.isdigit() and len(part) == 2 for part in parts)


def _fake_embed_text(
    text: str,
    size: int = 256,
    provider: str | None = None,
    model: str | None = None,
) -> list[float]:
    """Deterministic embedding stub for tests without external API calls."""
    buckets = [0.0] * max(size, 8)
    prefix = f"{provider or 'openai'}:{model or 'model'}".encode("utf-8")
    for token in text.lower().split():
        digest = hashlib.sha256(prefix + b"::" + token.encode("utf-8")).digest()
        buckets[digest[0] % len(buckets)] += 1.0
    return buckets


def _set_runtime_store_for_tests(data_dir: Path):
    """Point the shared runtime store to an isolated test database."""
    original_store = RUNTIME.store
    RUNTIME.store = MetadataStore(data_dir / "metadata.db")
    return original_store


def test_ingest_and_query_roundtrip() -> None:
    """Ensure ingestion builds indexes and query returns citations."""
    original_embed = index_chroma.embed_text
    original_provider = SETTINGS.llm_provider
    original_openai_key = SETTINGS.openai_api_key
    original_use_neo4j = SETTINGS.use_neo4j
    original_neo4j_uri = SETTINGS.neo4j_uri
    original_neo4j_user = SETTINGS.neo4j_user
    original_neo4j_password = SETTINGS.neo4j_password
    index_chroma.embed_text = _fake_embed_text
    SETTINGS.llm_provider = "openai"
    SETTINGS.openai_api_key = "test-key"
    SETTINGS.use_neo4j = True
    SETTINGS.neo4j_uri = "bolt://test-neo4j:7687"
    SETTINGS.neo4j_user = "neo4j"
    SETTINGS.neo4j_password = "password"

    service = RagApplicationService()
    service.graph_store.replace_edges = lambda source_id, edges: None
    service.graph_store.expand_paths = (
        lambda query, hops, max_paths: []
    )
    service.graph_store.clear_all_edges = lambda: 0
    service.graph_store.close = lambda: None
    try:
        result = service.ingest(
            IngestionRequest(
                source=SourceConfig(
                    source_type="folder",
                    local_path="sample_data",
                )
            )
        )
        assert result["status"] == "completed"
        assert isinstance(result.get("steps"), list)
        assert len(result.get("steps", [])) > 0
        assert isinstance(result.get("metrics"), dict)
        metrics = result.get("metrics", {})
        assert isinstance(metrics, dict)
        assert "elapsed_ms" not in metrics
        assert _looks_like_hhmmss(metrics.get("elapsed_hhmmss"))
        deduplication = result.get("deduplication", {})
        assert isinstance(deduplication, dict)
        assert isinstance(deduplication.get("incoming_batch"), dict)
        assert isinstance(deduplication.get("replaced_existing"), dict)

        first_step = result.get("steps", [])[0]
        assert isinstance(first_step, dict)
        assert "elapsed_ms" not in first_step
        assert _looks_like_hhmmss(first_step.get("elapsed_hhmmss"))

        response = service.query(
            QueryRequest(
                question="Who works on Project Atlas?",
                include_llm_answer=False,
            )
        )
        assert response.answer == ""
        assert len(response.citations) > 0
        assert response.diagnostics.get("requested_mode") == "retrieval_only"
        assert response.diagnostics.get("llm_invoked") is False
    finally:
        service.close()
        index_chroma.embed_text = original_embed
        SETTINGS.llm_provider = original_provider
        SETTINGS.openai_api_key = original_openai_key
        SETTINGS.use_neo4j = original_use_neo4j
        SETTINGS.neo4j_uri = original_neo4j_uri
        SETTINGS.neo4j_user = original_neo4j_user
        SETTINGS.neo4j_password = original_neo4j_password


def test_reset_all_clears_repositories(tmp_path) -> None:
    """Ensure reset operation clears persisted and in-memory retrieval data."""
    original_embed = index_chroma.embed_text
    original_provider = SETTINGS.llm_provider
    original_openai_key = SETTINGS.openai_api_key
    original_use_neo4j = SETTINGS.use_neo4j
    original_neo4j_uri = SETTINGS.neo4j_uri
    original_neo4j_user = SETTINGS.neo4j_user
    original_neo4j_password = SETTINGS.neo4j_password
    original_data_dir = SETTINGS.data_dir
    original_chroma_persist_dir = SETTINGS.chroma_persist_dir
    index_chroma.embed_text = _fake_embed_text
    SETTINGS.llm_provider = "openai"
    SETTINGS.openai_api_key = "test-key"
    SETTINGS.use_neo4j = True
    SETTINGS.neo4j_uri = "bolt://test-neo4j:7687"
    SETTINGS.neo4j_user = "neo4j"
    SETTINGS.neo4j_password = "password"
    SETTINGS.data_dir = tmp_path / "storage"
    SETTINGS.chroma_persist_dir = SETTINGS.data_dir / "chromadb"
    original_store = _set_runtime_store_for_tests(SETTINGS.data_dir)

    service = RagApplicationService()
    service.graph_store.replace_edges = lambda source_id, edges: None
    service.graph_store.expand_paths = (
        lambda query, hops, max_paths: []
    )
    service.graph_store.clear_all_edges = lambda: 0
    service.graph_store.close = lambda: None
    try:
        service.ingest(
            IngestionRequest(
                source=SourceConfig(
                    source_type="folder",
                    local_path="sample_data",
                )
            )
        )

        before_reset = service.query(
            QueryRequest(
                question="Who works on Project Atlas?",
                force_fallback=True,
            )
        )
        assert len(before_reset.citations) > 0

        reset = service.reset_all()
        assert reset.status == "completed"
        assert reset.deleted_documents >= 1
        assert reset.deleted_chunks >= 1
        assert reset.deleted_jobs >= 1

        after_reset = service.query(
            QueryRequest(
                question="Who works on Project Atlas?",
                force_fallback=True,
            )
        )
        assert len(after_reset.citations) == 0
    finally:
        service.close()
        index_chroma.embed_text = original_embed
        SETTINGS.llm_provider = original_provider
        SETTINGS.openai_api_key = original_openai_key
        SETTINGS.use_neo4j = original_use_neo4j
        SETTINGS.neo4j_uri = original_neo4j_uri
        SETTINGS.neo4j_user = original_neo4j_user
        SETTINGS.neo4j_password = original_neo4j_password
        SETTINGS.data_dir = original_data_dir
        SETTINGS.chroma_persist_dir = original_chroma_persist_dir
        RUNTIME.store = original_store


def test_ingest_job_status_includes_steps_and_progress() -> None:
    """Ensure job polling payload exposes persisted timeline details."""
    original_embed = index_chroma.embed_text
    original_provider = SETTINGS.llm_provider
    original_openai_key = SETTINGS.openai_api_key
    original_use_neo4j = SETTINGS.use_neo4j
    original_neo4j_uri = SETTINGS.neo4j_uri
    original_neo4j_user = SETTINGS.neo4j_user
    original_neo4j_password = SETTINGS.neo4j_password
    index_chroma.embed_text = _fake_embed_text
    SETTINGS.llm_provider = "openai"
    SETTINGS.openai_api_key = "test-key"
    SETTINGS.use_neo4j = True
    SETTINGS.neo4j_uri = "bolt://test-neo4j:7687"
    SETTINGS.neo4j_user = "neo4j"
    SETTINGS.neo4j_password = "password"

    service = RagApplicationService()
    service.graph_store.replace_edges = lambda source_id, edges: None
    service.graph_store.expand_paths = (
        lambda query, hops, max_paths: []
    )
    service.graph_store.clear_all_edges = lambda: 0
    service.graph_store.close = lambda: None
    try:
        result = service.ingest(
            IngestionRequest(
                source=SourceConfig(
                    source_type="folder",
                    local_path="sample_data",
                )
            )
        )
        job_id = str(result.get("job_id", ""))
        assert job_id

        job = service.get_job(job_id)
        assert isinstance(job, dict)
        assert float(job.get("progress_pct", 0.0)) == 100.0

        steps = job.get("steps")
        assert isinstance(steps, list)
        assert len(steps) > 0
        first_step = steps[0]
        assert isinstance(first_step, dict)
        assert "elapsed_ms" not in first_step
        assert _looks_like_hhmmss(first_step.get("elapsed_hhmmss"))
        assert any(
            isinstance(step, dict)
            and step.get("name") == "ingestion_completed"
            for step in steps
        )
    finally:
        service.close()
        index_chroma.embed_text = original_embed
        SETTINGS.llm_provider = original_provider
        SETTINGS.openai_api_key = original_openai_key
        SETTINGS.use_neo4j = original_use_neo4j
        SETTINGS.neo4j_uri = original_neo4j_uri
        SETTINGS.neo4j_user = original_neo4j_user
        SETTINGS.neo4j_password = original_neo4j_password


def test_query_refreshes_stale_indexes_after_external_ingestion() -> None:
    """Ensure query refreshes indexes when ingestion happened in another service."""
    original_embed = index_chroma.embed_text
    original_provider = SETTINGS.llm_provider
    original_openai_key = SETTINGS.openai_api_key
    original_use_neo4j = SETTINGS.use_neo4j
    original_neo4j_uri = SETTINGS.neo4j_uri
    original_neo4j_user = SETTINGS.neo4j_user
    original_neo4j_password = SETTINGS.neo4j_password
    index_chroma.embed_text = _fake_embed_text
    SETTINGS.llm_provider = "openai"
    SETTINGS.openai_api_key = "test-key"
    SETTINGS.use_neo4j = True
    SETTINGS.neo4j_uri = "bolt://test-neo4j:7687"
    SETTINGS.neo4j_user = "neo4j"
    SETTINGS.neo4j_password = "password"

    api_service = RagApplicationService()
    worker_service = RagApplicationService()
    api_service.graph_store.replace_edges = lambda source_id, edges: None
    api_service.graph_store.expand_paths = (
        lambda query, hops, max_paths: []
    )
    api_service.graph_store.clear_all_edges = lambda: 0
    api_service.graph_store.close = lambda: None
    worker_service.graph_store.replace_edges = (
        lambda source_id, edges: None
    )
    worker_service.graph_store.expand_paths = (
        lambda query, hops, max_paths: []
    )
    worker_service.graph_store.clear_all_edges = lambda: 0
    worker_service.graph_store.close = lambda: None

    try:
        api_service.reset_all()
        assert len(api_service.bm25_index._chunks) == 0

        ingest = worker_service.ingest(
            IngestionRequest(
                source=SourceConfig(
                    source_type="folder",
                    local_path="sample_data",
                )
            )
        )
        source_id = str(ingest.get("source_id", ""))
        assert source_id

        # API service still has stale in-memory BM25 before query-triggered
        # version refresh.
        assert len(api_service.bm25_index._chunks) == 0

        refreshed = api_service.query(
            QueryRequest(
                question="Who works on Project Atlas?",
                source_id=source_id,
                force_fallback=True,
            )
        )
        assert len(refreshed.citations) > 0
        assert len(api_service.bm25_index._chunks) > 0
    finally:
        api_service.close()
        worker_service.close()
        index_chroma.embed_text = original_embed
        SETTINGS.llm_provider = original_provider
        SETTINGS.openai_api_key = original_openai_key
        SETTINGS.use_neo4j = original_use_neo4j
        SETTINGS.neo4j_uri = original_neo4j_uri
        SETTINGS.neo4j_user = original_neo4j_user
        SETTINGS.neo4j_password = original_neo4j_password


def test_ingest_replaces_previous_duplicate_documents_globally(tmp_path) -> None:
    """Re-ingesting a title/type match should delete the older version first."""
    original_embed = index_chroma.embed_text
    original_provider = SETTINGS.llm_provider
    original_openai_key = SETTINGS.openai_api_key
    original_use_neo4j = SETTINGS.use_neo4j
    original_neo4j_uri = SETTINGS.neo4j_uri
    original_neo4j_user = SETTINGS.neo4j_user
    original_neo4j_password = SETTINGS.neo4j_password
    original_data_dir = SETTINGS.data_dir
    original_chroma_persist_dir = SETTINGS.chroma_persist_dir
    index_chroma.embed_text = _fake_embed_text
    SETTINGS.llm_provider = "openai"
    SETTINGS.openai_api_key = "test-key"
    SETTINGS.use_neo4j = True
    SETTINGS.neo4j_uri = "bolt://test-neo4j:7687"
    SETTINGS.neo4j_user = "neo4j"
    SETTINGS.neo4j_password = "password"
    SETTINGS.data_dir = tmp_path / "storage"
    SETTINGS.chroma_persist_dir = SETTINGS.data_dir / "chromadb"
    original_store = _set_runtime_store_for_tests(SETTINGS.data_dir)

    old_root = SETTINGS.data_dir / "ingestion_staging" / "old-copy"
    new_root = SETTINGS.data_dir / "ingestion_staging" / "new-copy"
    old_root.mkdir(parents=True, exist_ok=True)
    new_root.mkdir(parents=True, exist_ok=True)
    old_file = old_root / "atlas.md"
    new_file = new_root / "atlas.md"
    old_file.write_text("Project Atlas is led by Alice.", encoding="utf-8")
    new_file.write_text("Project Atlas is led by Bob.", encoding="utf-8")

    service = RagApplicationService()
    graph_calls: list[tuple[str, int]] = []
    service.graph_store.replace_edges = (
        lambda source_id, edges: graph_calls.append((source_id, len(edges)))
        or {"relationships_created": len(edges)}
    )
    service.graph_store.expand_paths = (
        lambda query, hops, max_paths, source_id=None: []
    )
    service.graph_store.clear_all_edges = lambda: 0
    service.graph_store.close = lambda: None
    try:
        first = service.ingest(
            IngestionRequest(
                source=SourceConfig(
                    source_type="folder",
                    local_path=str(old_root),
                )
            )
        )
        first_source_id = str(first.get("source_id", ""))
        assert first.get("status") == "completed"
        assert old_file.exists()

        second = service.ingest(
            IngestionRequest(
                source=SourceConfig(
                    source_type="folder",
                    local_path=str(new_root),
                )
            )
        )
        second_source_id = str(second.get("source_id", ""))
        assert second.get("status") == "completed"
        assert first_source_id != second_source_id

        documents = service.list_documents()
        chunks = service.store.list_chunks()
        dedup_step = next(
            step
            for step in second.get("steps", [])
            if isinstance(step, dict)
            and step.get("name") == "deduplicate_documents"
        )

        assert len(documents) == 1
        assert documents[0].source_id == second_source_id
        assert Path(documents[0].path_or_url).resolve(strict=False) == new_file
        assert len(chunks) >= 1
        assert all(chunk.source_id == second_source_id for chunk in chunks)
        assert not old_file.exists()
        assert dedup_step.get("details", {}).get("deleted_documents") == 1
        assert dedup_step.get("details", {}).get("deleted_staging_files") == 1
        assert second.get("deduplication", {}).get(
            "replaced_existing", {}
        ).get("replaced_paths") == [str(old_file)]
        assert any(source_id == first_source_id for source_id, _ in graph_calls)
        assert any(source_id == second_source_id for source_id, _ in graph_calls)
    finally:
        service.close()
        index_chroma.embed_text = original_embed
        SETTINGS.llm_provider = original_provider
        SETTINGS.openai_api_key = original_openai_key
        SETTINGS.use_neo4j = original_use_neo4j
        SETTINGS.neo4j_uri = original_neo4j_uri
        SETTINGS.neo4j_user = original_neo4j_user
        SETTINGS.neo4j_password = original_neo4j_password
        SETTINGS.data_dir = original_data_dir
        SETTINGS.chroma_persist_dir = original_chroma_persist_dir
        RUNTIME.store = original_store


def test_ingest_collapses_duplicate_documents_within_same_batch(tmp_path) -> None:
    """A single folder ingest should keep one document per title/type key."""
    original_embed = index_chroma.embed_text
    original_provider = SETTINGS.llm_provider
    original_openai_key = SETTINGS.openai_api_key
    original_use_neo4j = SETTINGS.use_neo4j
    original_neo4j_uri = SETTINGS.neo4j_uri
    original_neo4j_user = SETTINGS.neo4j_user
    original_neo4j_password = SETTINGS.neo4j_password
    original_data_dir = SETTINGS.data_dir
    original_chroma_persist_dir = SETTINGS.chroma_persist_dir
    index_chroma.embed_text = _fake_embed_text
    SETTINGS.llm_provider = "openai"
    SETTINGS.openai_api_key = "test-key"
    SETTINGS.use_neo4j = True
    SETTINGS.neo4j_uri = "bolt://test-neo4j:7687"
    SETTINGS.neo4j_user = "neo4j"
    SETTINGS.neo4j_password = "password"
    SETTINGS.data_dir = tmp_path / "storage"
    SETTINGS.chroma_persist_dir = SETTINGS.data_dir / "chromadb"
    original_store = _set_runtime_store_for_tests(SETTINGS.data_dir)

    batch_root = tmp_path / "incoming"
    first_copy = batch_root / "a" / "atlas.md"
    second_copy = batch_root / "b" / "atlas.md"
    first_copy.parent.mkdir(parents=True, exist_ok=True)
    second_copy.parent.mkdir(parents=True, exist_ok=True)
    first_copy.write_text("Project Atlas is led by Alice.", encoding="utf-8")
    second_copy.write_text("Project Atlas is led by Bob.", encoding="utf-8")

    service = RagApplicationService()
    service.graph_store.replace_edges = (
        lambda source_id, edges: {"relationships_created": len(edges)}
    )
    service.graph_store.expand_paths = (
        lambda query, hops, max_paths, source_id=None: []
    )
    service.graph_store.clear_all_edges = lambda: 0
    service.graph_store.close = lambda: None
    try:
        result = service.ingest(
            IngestionRequest(
                source=SourceConfig(
                    source_type="folder",
                    local_path=str(batch_root),
                )
            )
        )

        documents = service.list_documents()
        doc_map = service.store.get_document_map()
        batch_step = next(
            step
            for step in result.get("steps", [])
            if isinstance(step, dict)
            and step.get("name") == "deduplicate_incoming_batch"
        )

        assert result.get("status") == "completed"
        assert len(documents) == 1
        assert Path(documents[0].path_or_url).resolve(strict=False) == second_copy
        assert len(doc_map) == 1
        assert next(iter(doc_map.values())).get("title") == "atlas"
        assert batch_step.get("details", {}).get("skipped_documents") == 1
        assert batch_step.get("details", {}).get("kept_documents") == 1
        assert result.get("deduplication", {}).get("incoming_batch", {}).get(
            "kept_paths"
        ) == [str(second_copy)]
    finally:
        service.close()
        index_chroma.embed_text = original_embed
        SETTINGS.llm_provider = original_provider
        SETTINGS.openai_api_key = original_openai_key
        SETTINGS.use_neo4j = original_use_neo4j
        SETTINGS.neo4j_uri = original_neo4j_uri
        SETTINGS.neo4j_user = original_neo4j_user
        SETTINGS.neo4j_password = original_neo4j_password
        SETTINGS.data_dir = original_data_dir
        SETTINGS.chroma_persist_dir = original_chroma_persist_dir
        RUNTIME.store = original_store


def test_stale_query_refresh_does_not_rebuild_vector_embeddings() -> None:
    """Avoid expensive vector re-embedding on first query after async ingest."""
    original_embed = index_chroma.embed_text
    original_provider = SETTINGS.llm_provider
    original_openai_key = SETTINGS.openai_api_key
    original_use_neo4j = SETTINGS.use_neo4j
    original_neo4j_uri = SETTINGS.neo4j_uri
    original_neo4j_user = SETTINGS.neo4j_user
    original_neo4j_password = SETTINGS.neo4j_password
    index_chroma.embed_text = _fake_embed_text
    SETTINGS.llm_provider = "openai"
    SETTINGS.openai_api_key = "test-key"
    SETTINGS.use_neo4j = True
    SETTINGS.neo4j_uri = "bolt://test-neo4j:7687"
    SETTINGS.neo4j_user = "neo4j"
    SETTINGS.neo4j_password = "password"

    api_service = RagApplicationService()
    worker_service = RagApplicationService()
    api_service.graph_store.replace_edges = lambda source_id, edges: None
    api_service.graph_store.expand_paths = (
        lambda query, hops, max_paths: []
    )
    api_service.graph_store.clear_all_edges = lambda: 0
    api_service.graph_store.close = lambda: None
    worker_service.graph_store.replace_edges = (
        lambda source_id, edges: None
    )
    worker_service.graph_store.expand_paths = (
        lambda query, hops, max_paths: []
    )
    worker_service.graph_store.clear_all_edges = lambda: 0
    worker_service.graph_store.close = lambda: None

    vector_rebuild_calls: list[object] = []
    original_vector_rebuild = api_service.vector_index.rebuild

    def _record_vector_rebuild(chunks: object) -> None:
        vector_rebuild_calls.append(chunks)
        original_vector_rebuild(chunks)

    try:
        api_service.reset_all()

        ingest = worker_service.ingest(
            IngestionRequest(
                source=SourceConfig(
                    source_type="folder",
                    local_path="sample_data",
                )
            )
        )
        source_id = str(ingest.get("source_id", ""))
        assert source_id

        api_service.vector_index.rebuild = _record_vector_rebuild
        refreshed = api_service.query(
            QueryRequest(
                question="Who works on Project Atlas?",
                source_id=source_id,
                force_fallback=True,
            )
        )
        assert len(refreshed.citations) > 0
        assert len(vector_rebuild_calls) == 0
    finally:
        api_service.close()
        worker_service.close()
        index_chroma.embed_text = original_embed
        SETTINGS.llm_provider = original_provider
        SETTINGS.openai_api_key = original_openai_key
        SETTINGS.use_neo4j = original_use_neo4j
        SETTINGS.neo4j_uri = original_neo4j_uri
        SETTINGS.neo4j_user = original_neo4j_user
        SETTINGS.neo4j_password = original_neo4j_password


def test_query_source_id_filters_out_other_sources() -> None:
    """Ensure source_id in query constrains retrieval results."""
    original_embed = index_chroma.embed_text
    original_provider = SETTINGS.llm_provider
    original_openai_key = SETTINGS.openai_api_key
    original_use_neo4j = SETTINGS.use_neo4j
    original_neo4j_uri = SETTINGS.neo4j_uri
    original_neo4j_user = SETTINGS.neo4j_user
    original_neo4j_password = SETTINGS.neo4j_password
    index_chroma.embed_text = _fake_embed_text
    SETTINGS.llm_provider = "openai"
    SETTINGS.openai_api_key = "test-key"
    SETTINGS.use_neo4j = True
    SETTINGS.neo4j_uri = "bolt://test-neo4j:7687"
    SETTINGS.neo4j_user = "neo4j"
    SETTINGS.neo4j_password = "password"

    service = RagApplicationService()
    service.graph_store.replace_edges = lambda source_id, edges: None
    service.graph_store.expand_paths = (
        lambda query, hops, max_paths: []
    )
    service.graph_store.clear_all_edges = lambda: 0
    service.graph_store.close = lambda: None
    try:
        service.reset_all()
        result = service.ingest(
            IngestionRequest(
                source=SourceConfig(
                    source_type="folder",
                    local_path="sample_data",
                )
            )
        )
        source_id = str(result.get("source_id", ""))
        assert source_id

        matching = service.query(
            QueryRequest(
                question="Project Atlas",
                source_id=source_id,
                force_fallback=True,
            )
        )
        assert len(matching.citations) > 0

        missing = service.query(
            QueryRequest(
                question="Project Atlas",
                source_id="missing-source-id",
                force_fallback=True,
            )
        )
        assert len(missing.citations) == 0
    finally:
        service.close()
        index_chroma.embed_text = original_embed
        SETTINGS.llm_provider = original_provider
        SETTINGS.openai_api_key = original_openai_key
        SETTINGS.use_neo4j = original_use_neo4j
        SETTINGS.neo4j_uri = original_neo4j_uri
        SETTINGS.neo4j_user = original_neo4j_user
        SETTINGS.neo4j_password = original_neo4j_password


def test_query_document_ids_filter_to_selected_documents() -> None:
    """Ensure document_ids narrows retrieval to the selected documents only."""
    original_embed = index_chroma.embed_text
    original_provider = SETTINGS.llm_provider
    original_openai_key = SETTINGS.openai_api_key
    original_use_neo4j = SETTINGS.use_neo4j
    original_neo4j_uri = SETTINGS.neo4j_uri
    original_neo4j_user = SETTINGS.neo4j_user
    original_neo4j_password = SETTINGS.neo4j_password
    index_chroma.embed_text = _fake_embed_text
    SETTINGS.llm_provider = "openai"
    SETTINGS.openai_api_key = "test-key"
    SETTINGS.use_neo4j = True
    SETTINGS.neo4j_uri = "bolt://test-neo4j:7687"
    SETTINGS.neo4j_user = "neo4j"
    SETTINGS.neo4j_password = "password"

    service = RagApplicationService()
    service.graph_store.replace_edges = lambda source_id, edges: None
    service.graph_store.expand_paths = (
        lambda query, hops, max_paths: []
    )
    service.graph_store.clear_all_edges = lambda: 0
    service.graph_store.close = lambda: None
    try:
        service.reset_all()
        result = service.ingest(
            IngestionRequest(
                source=SourceConfig(
                    source_type="folder",
                    local_path="sample_data",
                )
            )
        )
        source_id = str(result.get("source_id", ""))
        assert source_id

        documents = service.list_documents(source_id=source_id)
        engineering_doc = next(
            item
            for item in documents
            if item.path_or_url.replace("\\", "/").endswith("engineering.md")
        )
        finance_doc = next(
            item
            for item in documents
            if item.path_or_url.replace("\\", "/").endswith("policy_finance.md")
        )

        filtered = service.query(
            QueryRequest(
                question="Project Atlas",
                source_id=source_id,
                document_ids=[engineering_doc.document_id],
                force_fallback=True,
            )
        )
        assert len(filtered.citations) > 0
        assert {
            citation.document_id for citation in filtered.citations
        } == {engineering_doc.document_id}
        assert filtered.diagnostics.get("document_filter_count") == 1

        missing = service.query(
            QueryRequest(
                question="Project Atlas",
                source_id=source_id,
                document_ids=[finance_doc.document_id, "missing-doc-id"],
                force_fallback=True,
            )
        )
        assert len(missing.citations) > 0
        assert {
            citation.document_id for citation in missing.citations
        } == {finance_doc.document_id}
    finally:
        service.close()
        index_chroma.embed_text = original_embed
        SETTINGS.llm_provider = original_provider
        SETTINGS.openai_api_key = original_openai_key
        SETTINGS.use_neo4j = original_use_neo4j
        SETTINGS.neo4j_uri = original_neo4j_uri
        SETTINGS.neo4j_user = original_neo4j_user
        SETTINGS.neo4j_password = original_neo4j_password


