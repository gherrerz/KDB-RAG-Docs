"""Tests for LLM context assembly formatting."""

from __future__ import annotations

from coderag.core.models import ChunkRecord, GraphPath
from coderag.retrieval.context_assembler import assemble_context


def test_assemble_context_uses_document_name_not_chunk_id() -> None:
    """Prefer document names in context blocks used by remote LLMs."""
    chunk = ChunkRecord(
        chunk_id="c-123",
        document_id="doc-1",
        source_id="source-1",
        section_name="General",
        text="Data governance aligns architecture and stewardship.",
        start_ref=0,
        end_ref=56,
        metadata={},
    )
    graph_path = GraphPath(nodes=["Data", "Governance"], relationships=["rel"])

    context = assemble_context(
        chunks=[chunk],
        graph_paths=[graph_path],
        max_chars=2000,
        document_map={
            "doc-1": {
                "title": "Planificacion_Estrategica.md",
                "path_or_url": "sample_data/Planificacion_Estrategica.md",
            }
        },
    )

    assert "[Documento Planificacion_Estrategica.md]" in context
    assert "[Chunk" not in context
    assert "[GraphPath] Data -> Governance" in context


def test_assemble_context_prefers_filename_when_title_has_no_extension() -> None:
    """Use filename from path when title metadata omits extension."""
    chunk = ChunkRecord(
        chunk_id="c-200",
        document_id="doc-200",
        source_id="source-1",
        section_name="General",
        text="Las capacidades de datos deben incluir calidad y seguridad.",
        start_ref=10,
        end_ref=64,
        metadata={},
    )

    context = assemble_context(
        chunks=[chunk],
        graph_paths=[],
        max_chars=2000,
        document_map={
            "doc-200": {
                "title": "DM_GobiernoDelDato",
                "path_or_url": "storage/ingestion_staging/DM_GobiernoDelDato.pdf",
            }
        },
    )

    assert "[Documento DM_GobiernoDelDato.pdf]" in context
    assert "[Documento DM_GobiernoDelDato]" not in context


def test_assemble_context_interleaves_documents_before_truncation() -> None:
    """Preserve multi-document coverage when context budget is limited."""
    chunks = [
        ChunkRecord(
            chunk_id="a-1",
            document_id="doc-a",
            source_id="source-1",
            section_name="General",
            text="A" * 220,
            start_ref=0,
            end_ref=220,
            metadata={},
        ),
        ChunkRecord(
            chunk_id="a-2",
            document_id="doc-a",
            source_id="source-1",
            section_name="General",
            text="B" * 220,
            start_ref=220,
            end_ref=440,
            metadata={},
        ),
        ChunkRecord(
            chunk_id="b-1",
            document_id="doc-b",
            source_id="source-1",
            section_name="General",
            text="C" * 220,
            start_ref=0,
            end_ref=220,
            metadata={},
        ),
    ]

    context = assemble_context(
        chunks=chunks,
        graph_paths=[],
        max_chars=650,
        document_map={
            "doc-a": {
                "title": "DocA.md",
                "path_or_url": "sample_data/DocA.md",
            },
            "doc-b": {
                "title": "DocB.md",
                "path_or_url": "sample_data/DocB.md",
            },
        },
    )

    assert "[Documento DocA.md]" in context
    assert "[Documento DocB.md]" in context
