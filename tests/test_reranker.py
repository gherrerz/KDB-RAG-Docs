"""Tests for reranking behavior in complex multi-document queries."""

from __future__ import annotations

from coderag.core.models import ChunkRecord
from coderag.retrieval.reranker import rerank_results


def _chunk(chunk_id: str, doc_id: str, text: str) -> ChunkRecord:
    """Build chunk record with consistent defaults for ranking tests."""
    return ChunkRecord(
        chunk_id=chunk_id,
        document_id=doc_id,
        source_id="source-1",
        section_name="General",
        text=text,
        start_ref=0,
        end_ref=len(text),
        metadata={},
    )


def test_rerank_results_preserves_document_diversity_for_complex_query() -> None:
    """Avoid returning only one document when multiple are relevant."""
    items = [
        (
            _chunk(
                "c1",
                "doc-a",
                "Gobierno de datos define roles y calidad operacional.",
            ),
            0.99,
            {"vector": 0.99, "bm25": 0.80},
        ),
        (
            _chunk(
                "c2",
                "doc-a",
                "La estrategia de datos coordina capacidades de negocio.",
            ),
            0.98,
            {"vector": 0.98, "bm25": 0.75},
        ),
        (
            _chunk(
                "c3",
                "doc-b",
                "Gestion estrategica conecta objetivos y gobierno de datos.",
            ),
            0.91,
            {"vector": 0.91, "bm25": 0.70},
        ),
    ]

    ranked = rerank_results(
        query=(
            "Como se relaciona gobierno de datos con gestion estrategica "
            "y objetivos de negocio"
        ),
        items=items,
        top_k=3,
    )

    returned_docs = {chunk.document_id for chunk, _score, _parts in ranked}
    assert "doc-a" in returned_docs
    assert "doc-b" in returned_docs


def test_rerank_results_keeps_simple_query_focus() -> None:
    """Keep dominant document for short and specific queries."""
    items = [
        (
            _chunk("c1", "doc-a", "Policy FIN-001 requires dual approval."),
            0.95,
            {"vector": 0.95, "bm25": 0.88},
        ),
        (
            _chunk("c2", "doc-b", "Project Atlas budget baseline overview."),
            0.70,
            {"vector": 0.70, "bm25": 0.50},
        ),
    ]

    ranked = rerank_results(
        query="FIN-001",
        items=items,
        top_k=1,
    )

    assert len(ranked) == 1
    assert ranked[0][0].document_id == "doc-a"


def test_rerank_results_mmr_reduces_redundant_chunks() -> None:
    """Prefer semantically distinct chunks for complex multi-part questions."""
    items = [
        (
            _chunk(
                "c1",
                "doc-a",
                "Project Atlas budget governance and monthly cadence.",
            ),
            0.97,
            {"vector": 0.97, "bm25": 0.90},
        ),
        (
            _chunk(
                "c2",
                "doc-a",
                "Project Atlas budget governance and monthly cadence.",
            ),
            0.96,
            {"vector": 0.96, "bm25": 0.89},
        ),
        (
            _chunk(
                "c3",
                "doc-b",
                "Procedure ENG-DELIVERY depends on Policy FIN-001.",
            ),
            0.93,
            {"vector": 0.93, "bm25": 0.81},
        ),
    ]

    ranked = rerank_results(
        query=(
            "How does Project Atlas budget governance connect to "
            "ENG-DELIVERY and FIN-001 policy"
        ),
        items=items,
        top_k=2,
    )

    returned_ids = [chunk.chunk_id for chunk, _score, _parts in ranked]
    assert "c1" in returned_ids or "c2" in returned_ids
    assert "c3" in returned_ids
