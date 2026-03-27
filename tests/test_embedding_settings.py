"""Tests for provider and embedding model environment resolution."""

from __future__ import annotations

import pytest

from coderag.core.settings import Settings


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


def test_embedding_provider_must_be_external_under_strict_mode() -> None:
    """Reject local provider when embeddings must come from API providers."""
    settings = Settings(llm_provider="local")
    with pytest.raises(RuntimeError):
        settings.require_embedding_provider_configured()


def test_embedding_provider_requires_credentials() -> None:
    """Fail validation when selected provider has no credentials."""
    settings = Settings(llm_provider="openai", openai_api_key=None)
    with pytest.raises(RuntimeError):
        settings.require_embedding_provider_configured()


def test_chroma_must_be_enabled_in_runtime() -> None:
    """Fail fast when vector runtime is not configured for Chroma."""
    settings = Settings(use_chroma=False)
    with pytest.raises(RuntimeError):
        settings.require_chroma_enabled()
