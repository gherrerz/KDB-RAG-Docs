"""Tests for GraphStore expand_paths entity fallback behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from coderag.core.graph_store import GraphStore


@dataclass
class _Call:
    """Track Cypher calls for assertions."""

    query: str
    params: Dict[str, Any]


class _FakeSession:
    """Minimal Neo4j-like session for expand_paths tests."""

    def __init__(
        self,
        seed_names: List[str],
        path_rows: List[Dict[str, Any]],
    ) -> None:
        self.seed_names = seed_names
        self.path_rows = path_rows
        self.calls: List[_Call] = []

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type, exc, tb

    def run(self, query: str, **params: Any):
        self.calls.append(_Call(query=query, params=params))
        if "RETURN DISTINCT e.name AS name" in query:
            return [{"name": name} for name in self.seed_names]
        return self.path_rows


class _FakeDriver:
    """Minimal Neo4j-like driver wrapper."""

    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def session(self) -> _FakeSession:
        return self._session


def test_expand_paths_uses_capitalized_entities_without_seed_lookup() -> None:
    """Skip lowercase seed lookup when entities are already detected."""
    path_rows = [
        {
            "nodes": ["Gobierno de datos", "Estrategia"],
            "relationships": ["RELATES_TO"],
        }
    ]
    session = _FakeSession(seed_names=["unused"], path_rows=path_rows)
    store = GraphStore()
    store._get_driver = lambda: _FakeDriver(session)

    paths = store.expand_paths(
        query="Como se relacionan Gobierno y Estrategia?",
        hops=2,
        max_paths=6,
    )

    assert len(paths) == 1
    assert paths[0].nodes == ["Gobierno de datos", "Estrategia"]
    seed_calls = [
        call for call in session.calls if "RETURN DISTINCT e.name AS name" in call.query
    ]
    assert len(seed_calls) == 0


def test_expand_paths_falls_back_to_lowercase_token_entity_seeds() -> None:
    """Resolve graph entities from lowercase query tokens when needed."""
    path_rows = [
        {
            "nodes": ["Gobierno de Datos", "Gestion Estrategica"],
            "relationships": ["RELATES_TO"],
        }
    ]
    session = _FakeSession(
        seed_names=["Gobierno de Datos"],
        path_rows=path_rows,
    )
    store = GraphStore()
    store._get_driver = lambda: _FakeDriver(session)

    paths = store.expand_paths(
        query="como se relacionan el gobierno de datos y la gestion estrategica",
        hops=2,
        max_paths=6,
    )

    assert len(paths) == 1
    assert paths[0].nodes == ["Gobierno de Datos", "Gestion Estrategica"]

    seed_calls = [
        call for call in session.calls if "RETURN DISTINCT e.name AS name" in call.query
    ]
    assert len(seed_calls) == 1
    tokens = seed_calls[0].params.get("tokens", [])
    assert isinstance(tokens, list)
    assert "datos" in tokens
    assert "estrategica" in tokens
