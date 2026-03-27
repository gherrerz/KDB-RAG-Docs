"""Tests for provider and embedding model environment resolution."""

from __future__ import annotations

from coderag.core.settings import Settings
from coderag.ingestion.embedding import embed_text


def test_vertex_alias_is_normalized() -> None:
    """Normalize vertex_ai alias to canonical vertex provider."""
    settings = Settings(llm_provider="vertex_ai")
    assert settings.resolve_llm_provider() == "vertex"
    assert settings.resolve_embedding_provider() == "vertex"


def test_embedding_model_global_override_wins() -> None:
    """Prefer LLM_EMBEDDING override over provider-specific defaults."""
    settings = Settings(
        llm_provider="gemini",
        llm_embedding="text-embedding-custom",
        gemini_embedding_model="text-embedding-004",
    )
    assert settings.resolve_embedding_model() == "text-embedding-custom"


def test_embedding_model_uses_provider_default() -> None:
    """Resolve embedding model from selected provider when no override."""
    settings = Settings(
        llm_provider="openai",
        llm_embedding=None,
        openai_embedding_model="text-embedding-3-large",
    )
    assert settings.resolve_embedding_model() == "text-embedding-3-large"


def test_embedding_vectors_change_with_model_selection() -> None:
    """Model selection should affect deterministic embedding output."""
    vec_a = embed_text(
        "Project Atlas dependency graph",
        size=64,
        provider="openai",
        model="text-embedding-3-small",
    )
    vec_b = embed_text(
        "Project Atlas dependency graph",
        size=64,
        provider="openai",
        model="text-embedding-3-large",
    )
    assert vec_a != vec_b
