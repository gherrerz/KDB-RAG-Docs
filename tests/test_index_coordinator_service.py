"""Unit tests for RetrievalIndexCoordinator extraction."""

from __future__ import annotations

from coderag.core.index_coordinator_service import RetrievalIndexCoordinator


class _StoreStub:
    """Store stub exposing chunks, document map, and index version."""

    def __init__(self, *, version: int = 0) -> None:
        self.version = version
        self.list_chunks_calls: list[dict[str, object]] = []
        self.get_document_map_calls: list[dict[str, object]] = []

    def list_chunks(self, source_id: str | None = None):  # type: ignore[no-untyped-def]
        self.list_chunks_calls.append({"source_id": source_id})
        return [{"chunk_id": "c1", "source_id": source_id}]

    def get_document_map(  # type: ignore[no-untyped-def]
        self,
        source_id: str | None = None,
    ):
        self.get_document_map_calls.append({"source_id": source_id})
        return {"doc-1": {"path_or_url": "sample_data/engineering.md"}}

    def get_index_version(self) -> int:
        return self.version


class _LexicalStub:
    """Lexical index stub recording rebuild invocations."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def rebuild(self, chunks, document_map):  # type: ignore[no-untyped-def]
        self.calls.append(
            {
                "chunks": list(chunks),
                "document_map": dict(document_map),
            }
        )


class _VectorStub:
    """Vector index stub recording rebuild invocations."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def rebuild(self, chunks):  # type: ignore[no-untyped-def]
        self.calls.append({"chunks": list(chunks)})


def test_rebuild_indexes_rebuilds_lexical_and_vector() -> None:
    """Full rebuild should refresh lexical and vector snapshots."""
    store = _StoreStub(version=7)
    lexical = _LexicalStub()
    vector = _VectorStub()
    coordinator = RetrievalIndexCoordinator(
        store=store,  # type: ignore[arg-type]
        lexical_index=lexical,  # type: ignore[arg-type]
        vector_index=vector,  # type: ignore[arg-type]
    )

    loaded_version = coordinator.rebuild_indexes(source_id="src-1")

    assert loaded_version == 7
    assert store.list_chunks_calls == [{"source_id": "src-1"}]
    assert store.get_document_map_calls == [{"source_id": "src-1"}]
    assert len(lexical.calls) == 1
    assert len(vector.calls) == 1


def test_rebuild_lexical_from_store_skips_vector_rebuild() -> None:
    """Lexical refresh path should not trigger vector re-embedding."""
    store = _StoreStub(version=11)
    lexical = _LexicalStub()
    vector = _VectorStub()
    coordinator = RetrievalIndexCoordinator(
        store=store,  # type: ignore[arg-type]
        lexical_index=lexical,  # type: ignore[arg-type]
        vector_index=vector,  # type: ignore[arg-type]
    )

    loaded_version = coordinator.rebuild_lexical_from_store()

    assert loaded_version == 11
    assert store.list_chunks_calls == [{"source_id": None}]
    assert store.get_document_map_calls == [{"source_id": None}]
    assert len(lexical.calls) == 1
    assert vector.calls == []


def test_ensure_fresh_indexes_refreshes_when_version_is_stale() -> None:
    """Cross-process refresh should run when persisted version changed."""
    store = _StoreStub(version=4)
    lexical = _LexicalStub()
    vector = _VectorStub()
    coordinator = RetrievalIndexCoordinator(
        store=store,  # type: ignore[arg-type]
        lexical_index=lexical,  # type: ignore[arg-type]
        vector_index=vector,  # type: ignore[arg-type]
    )

    loaded_version = coordinator.ensure_fresh_indexes(loaded_index_version=1)

    assert loaded_version == 4
    assert len(lexical.calls) == 1
    assert vector.calls == []


def test_ensure_fresh_indexes_skips_refresh_when_version_matches() -> None:
    """No-op refresh should preserve loaded version when already fresh."""
    store = _StoreStub(version=9)
    lexical = _LexicalStub()
    vector = _VectorStub()
    coordinator = RetrievalIndexCoordinator(
        store=store,  # type: ignore[arg-type]
        lexical_index=lexical,  # type: ignore[arg-type]
        vector_index=vector,  # type: ignore[arg-type]
    )

    loaded_version = coordinator.ensure_fresh_indexes(loaded_index_version=9)

    assert loaded_version == 9
    assert lexical.calls == []
    assert vector.calls == []