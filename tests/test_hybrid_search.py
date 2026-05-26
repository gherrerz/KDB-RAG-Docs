"""Unit tests for lexical + vector retrieval fusion."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from coderag.core.lexical_index import build_query_lexical_index
from coderag.core.models import ChunkRecord
from coderag.retrieval.hybrid_search import hybrid_search


def _chunk(chunk_id: str, document_id: str, text: str) -> ChunkRecord:
    """Create one stable chunk fixture for retrieval tests."""
    return ChunkRecord(
        chunk_id=chunk_id,
        document_id=document_id,
        source_id="source-1",
        section_name="General",
        text=text,
        start_ref=0,
        end_ref=len(text),
        metadata={},
    )


class _StubLexicalIndex:
    backend_label = "lexical"

    def __init__(self, hits: list[tuple[ChunkRecord, float]]) -> None:
        self._hits = hits

    def rebuild(self, chunks, document_map) -> None:
        return None

    def search(
        self,
        query: str,
        top_n: int,
        source_id: str | None = None,
        document_ids: list[str] | None = None,
    ) -> list[tuple[ChunkRecord, float]]:
        return self._hits[:top_n]

    def clear_all(self) -> None:
        return None


class _StubVectorIndex:
    def __init__(self, hits: list[tuple[ChunkRecord, float]]) -> None:
        self._hits = hits

    def search(
        self,
        query: str,
        top_n: int,
        source_id: str | None = None,
        document_ids: list[str] | None = None,
    ) -> list[tuple[ChunkRecord, float]]:
        return self._hits[:top_n]


def test_hybrid_search_reports_lexical_score_parts() -> None:
    """Expose lexical score parts instead of the retired BM25 label."""
    lexical_chunk = _chunk("chunk-1", "doc-1", "Project Atlas governance")
    vector_chunk = _chunk("chunk-2", "doc-2", "Atlas timeline and rollout")

    ranked = hybrid_search(
        query="Atlas governance",
        lexical_index=_StubLexicalIndex([(lexical_chunk, 3.0)]),
        vector_index=_StubVectorIndex([(vector_chunk, 2.0)]),
        top_n=2,
    )

    assert len(ranked) == 2
    assert "lexical" in ranked[0][2]
    assert "bm25" not in ranked[0][2]


def test_build_query_lexical_index_without_postgres_fails_on_use() -> None:
    """Disabled backend must fail explicitly when lexical runtime is missing."""
    settings = SimpleNamespace(resolve_postgres_dsn=lambda: "")

    index = build_query_lexical_index(settings)

    with pytest.raises(RuntimeError, match="LexicalStore Postgres"):
        index.search("atlas", top_n=5)