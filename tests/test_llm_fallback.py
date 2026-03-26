"""Tests for provider client fallback paths."""

from __future__ import annotations

from coderag.core.models import ChunkRecord
from coderag.llm.providerlmm_client import ProviderLlmClient


def test_local_fallback_without_chunks() -> None:
    """Return no-information message when no evidence chunks exist."""
    client = ProviderLlmClient()
    answer = client.answer(
        question="Who owns the budget process?",
        chunks=[],
        provider="openai",
        force_fallback=True,
    )
    assert "No se encontro informacion" in answer


def test_local_fallback_with_chunks() -> None:
    """Return extractive text when forced fallback has chunk evidence."""
    client = ProviderLlmClient()
    chunk = ChunkRecord(
        chunk_id="c1",
        document_id="d1",
        source_id="s1",
        section_name="General",
        text="Finance Department owns the annual Budget approval process.",
        start_ref=0,
        end_ref=60,
        metadata={},
    )
    answer = client.answer(
        question="Who owns budget approval?",
        chunks=[chunk],
        provider="gemini",
        force_fallback=True,
    )
    assert "Basado en la evidencia recuperada" in answer
