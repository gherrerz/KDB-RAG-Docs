"""Retrieval index coordination extracted from runtime facade."""

from __future__ import annotations

from coderag.core.lexical_index import QueryLexicalIndex
from coderag.core.protocols import RuntimeStoreProtocol, VectorIndexProtocol


class RetrievalIndexCoordinator:
    """Own retrieval index rebuild and cross-process refresh logic."""

    def __init__(
        self,
        *,
        store: RuntimeStoreProtocol,
        lexical_index: QueryLexicalIndex,
        vector_index: VectorIndexProtocol,
    ) -> None:
        """Build coordinator from persistent store and index adapters."""
        self._store = store
        self._lexical_index = lexical_index
        self._vector_index = vector_index

    def rebuild_indexes(self, source_id: str | None = None) -> int:
        """Rebuild lexical and vector indexes from persisted chunks."""
        chunks = self._store.list_chunks(source_id=source_id)
        document_map = self._store.get_document_map(source_id=source_id)
        self._lexical_index.rebuild(chunks, document_map)
        self._vector_index.rebuild(chunks)
        return self._store.get_index_version()

    def rebuild_lexical_from_store(self) -> int:
        """Refresh lexical retrieval only from persisted chunk snapshot."""
        self._lexical_index.rebuild(
            self._store.list_chunks(),
            self._store.get_document_map(),
        )
        return self._store.get_index_version()

    def refresh_after_external_update(self) -> int:
        """Refresh in-memory retrieval state after external ingestion."""
        return self.rebuild_lexical_from_store()

    def ensure_fresh_indexes(self, loaded_index_version: int) -> int:
        """Refresh indexes when another process bumped persisted version."""
        current_version = self._store.get_index_version()
        if current_version == loaded_index_version:
            return loaded_index_version
        return self.refresh_after_external_update()