"""Unit tests for core dependency composition wiring."""

from __future__ import annotations

from types import SimpleNamespace

import coderag.core.composition as composition


class _DummyRuntimeStore:
    pass


def test_build_service_dependencies_wires_expected_components(monkeypatch) -> None:
    """Build dependency set with expected runtime store and provider objects."""

    class _FakeSettings:
        embedding_size = 256
        llm_provider = "openai"
        llm_embedding = "text-embedding-3-small"

        def require_chroma_enabled(self) -> None:
            return None

    fake_runtime = SimpleNamespace(store=_DummyRuntimeStore())

    monkeypatch.setattr(
        composition,
        "build_query_lexical_index",
        lambda settings: {"kind": "lexical", "provider": settings.llm_provider},
    )
    monkeypatch.setattr(
        composition,
        "LocalVectorIndex",
        lambda size, provider, model: {
            "kind": "vector",
            "size": size,
            "provider": provider,
            "model": model,
        },
    )
    monkeypatch.setattr(
        composition,
        "ProviderLlmClient",
        lambda: {"kind": "llm"},
    )
    monkeypatch.setattr(
        composition,
        "GraphStore",
        lambda: {"kind": "graph"},
    )

    deps = composition.build_service_dependencies(
        settings=_FakeSettings(),
        runtime_state=fake_runtime,
    )

    assert deps.store is fake_runtime.store
    assert deps.lexical_index["kind"] == "lexical"
    assert deps.vector_index["kind"] == "vector"
    assert deps.llm_client["kind"] == "llm"
    assert deps.graph_store["kind"] == "graph"


def test_build_service_dependencies_requires_chroma_enabled(monkeypatch) -> None:
    """Service composition must call the chroma guard before wiring deps."""
    calls = {"require_chroma_enabled": 0}

    class _FakeSettings:
        embedding_size = 128
        llm_provider = "vertex"
        llm_embedding = "text-embedding-004"

        def require_chroma_enabled(self) -> None:
            calls["require_chroma_enabled"] += 1

    fake_runtime = SimpleNamespace(store=_DummyRuntimeStore())

    monkeypatch.setattr(
        composition,
        "build_query_lexical_index",
        lambda settings: {"kind": "lexical"},
    )
    monkeypatch.setattr(
        composition,
        "LocalVectorIndex",
        lambda size, provider, model: {"kind": "vector"},
    )
    monkeypatch.setattr(composition, "ProviderLlmClient", lambda: {"kind": "llm"})
    monkeypatch.setattr(composition, "GraphStore", lambda: {"kind": "graph"})

    composition.build_service_dependencies(
        settings=_FakeSettings(),
        runtime_state=fake_runtime,
    )

    assert calls["require_chroma_enabled"] == 1
