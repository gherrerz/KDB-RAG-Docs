"""Tests for provider client fallback paths."""

from __future__ import annotations

import pytest

from coderag.core.models import ChunkRecord
from coderag.core.settings import SETTINGS
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
    assert "## Resumen" in answer
    assert "Basado en la evidencia recuperada" in answer


def test_vertex_alias_uses_local_fallback() -> None:
    """Keep fallback behavior when provider is configured as vertex alias."""
    client = ProviderLlmClient()
    chunk = ChunkRecord(
        chunk_id="c2",
        document_id="d2",
        source_id="s2",
        section_name="General",
        text="Policy FIN-001 requires two-step approval.",
        start_ref=0,
        end_ref=45,
        metadata={},
    )
    answer = client.answer(
        question="What does FIN-001 require?",
        chunks=[chunk],
        provider="vertex",
        force_fallback=True,
    )
    assert "Basado en la evidencia recuperada" in answer


def test_strict_mode_fails_without_provider_credentials() -> None:
    """Raise RuntimeError when strict mode cannot call selected provider."""
    original_openai_api_key = SETTINGS.openai_api_key
    SETTINGS.openai_api_key = None

    client = ProviderLlmClient()
    chunk = ChunkRecord(
        chunk_id="c3",
        document_id="d3",
        source_id="s3",
        section_name="General",
        text="ISO 27001 defines requirements for ISMS.",
        start_ref=0,
        end_ref=42,
        metadata={},
    )
    try:
        with pytest.raises(RuntimeError):
            client.answer(
                question="What is ISO 27001?",
                chunks=[chunk],
                provider="openai",
                strict=True,
            )
    finally:
        SETTINGS.openai_api_key = original_openai_api_key


def test_openai_parses_output_content_when_output_text_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parse text from output[].content[] when output_text is not present."""
    original_openai_api_key = SETTINGS.openai_api_key
    SETTINGS.openai_api_key = "test-key"

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return

        @staticmethod
        def json() -> dict:
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "Respuesta desde output.content",
                            }
                        ],
                    }
                ]
            }

    def _fake_post(*_args, **_kwargs):
        return _FakeResponse()

    monkeypatch.setattr(
        "coderag.llm.providerlmm_client.requests.post",
        _fake_post,
    )

    client = ProviderLlmClient()
    chunk = ChunkRecord(
        chunk_id="c4",
        document_id="d4",
        source_id="s4",
        section_name="General",
        text="Texto de prueba para OpenAI parser.",
        start_ref=0,
        end_ref=32,
        metadata={},
    )

    try:
        answer = client.answer(
            question="Pregunta de prueba",
            chunks=[chunk],
            provider="openai",
            strict=True,
        )
        assert answer == "Respuesta desde output.content"
    finally:
        SETTINGS.openai_api_key = original_openai_api_key
