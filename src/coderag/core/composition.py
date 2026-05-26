"""Dependency composition helpers for runtime service wiring."""

from __future__ import annotations

from dataclasses import dataclass

from coderag.core.graph_store import GraphStore
from coderag.core.lexical_index import QueryLexicalIndex, build_query_lexical_index
from coderag.core.protocols import (
    GraphStoreProtocol,
    LlmClientProtocol,
    RuntimeStoreProtocol,
    VectorIndexProtocol,
)
from coderag.core.runtime import RUNTIME, RuntimeState
from coderag.core.settings import SETTINGS, Settings
from coderag.ingestion.index_chroma import LocalVectorIndex
from coderag.llm.providerlmm_client import ProviderLlmClient


@dataclass(frozen=True)
class ServiceDependencies:
    """Runtime dependencies required by the application service."""

    store: RuntimeStoreProtocol
    lexical_index: QueryLexicalIndex
    vector_index: VectorIndexProtocol
    llm_client: LlmClientProtocol
    graph_store: GraphStoreProtocol


def build_service_dependencies(
    settings: Settings = SETTINGS,
    runtime_state: RuntimeState = RUNTIME,
) -> ServiceDependencies:
    """Build one dependency set for `RagApplicationService` construction."""
    settings.require_chroma_enabled()
    return ServiceDependencies(
        store=runtime_state.store,
        lexical_index=build_query_lexical_index(settings),
        vector_index=LocalVectorIndex(
            size=settings.embedding_size,
            provider=settings.llm_provider,
            model=settings.llm_embedding,
        ),
        llm_client=ProviderLlmClient(),
        graph_store=GraphStore(),
    )