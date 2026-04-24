"""Tests for additive typed TDM graph operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from coderag.core.graph_store import GraphStore


@dataclass
class _Call:
    """Track cypher calls for assertions."""

    query: str
    params: Dict[str, Any]


class _FakeSession:
    """Minimal Neo4j-like session with write and read support."""

    def __init__(self, rows: List[Dict[str, Any]] | None = None) -> None:
        self.calls: List[_Call] = []
        self.rows = rows or []

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type, exc, tb

    def run(self, query: str, **params: Any):
        self.calls.append(_Call(query=query, params=params))
        if "DELETE r" in query or "DELETE n" in query:
            return _FakeResult(relationships_deleted=3)
        if "RETURN [n IN nodes(p) | n.name] AS nodes" in query:
            return self.rows
        if "RETURN DISTINCT e.name AS name" in query:
            return [{"name": "billing-api"}]
        return []

    def execute_write(self, fn, rows):
        fn(self, rows)


class _FakeDriver:
    """Minimal Neo4j-like driver wrapper."""

    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def session(self) -> _FakeSession:
        return self._session


class _Counters:
    """Minimal counters object used by fake result summaries."""

    def __init__(self, relationships_deleted: int) -> None:
        self.relationships_deleted = relationships_deleted


class _Summary:
    """Minimal summary object for GraphStore cleanup tests."""

    def __init__(self, relationships_deleted: int) -> None:
        self.counters = _Counters(relationships_deleted)


class _FakeResult:
    """Minimal result object that exposes consume()."""

    def __init__(self, relationships_deleted: int) -> None:
        self._relationships_deleted = relationships_deleted

    def consume(self) -> _Summary:
        return _Summary(self._relationships_deleted)


def test_replace_tdm_edges_writes_typed_relationships() -> None:
    """Persist typed TDM edges using TDM_REL relationship label."""
    session = _FakeSession()
    store = GraphStore()
    store.is_enabled = lambda: True
    store._get_driver = lambda: _FakeDriver(session)

    metrics = store.replace_tdm_edges(
        source_id="src-1",
        typed_edges=[
            ("billing-api", "USES_TABLE", "invoices", "src-1"),
            ("invoices", "HAS_COLUMN", "customer_email", "src-1"),
        ],
    )

    assert metrics["rows_written"] == 2
    unwind_calls = [call for call in session.calls if "UNWIND" in call.query]
    assert len(unwind_calls) == 1
    assert "TDM_REL" in unwind_calls[0].query


def test_expand_tdm_paths_supports_relation_filter() -> None:
    """Filter typed TDM path expansion by allowed relation types."""
    session = _FakeSession(
        rows=[
            {
                "nodes": ["billing-api", "invoices", "customer_email"],
                "relationships": ["USES_TABLE", "HAS_COLUMN"],
            }
        ]
    )
    store = GraphStore()
    store.is_enabled = lambda: True
    store._get_driver = lambda: _FakeDriver(session)

    paths = store.expand_tdm_paths(
        query="billing api usa invoices",
        hops=2,
        max_paths=6,
        source_id="src-1",
        rel_types=["USES_TABLE", "HAS_COLUMN"],
    )

    assert len(paths) == 1
    assert paths[0].nodes == ["billing-api", "invoices", "customer_email"]
    path_calls = [call for call in session.calls if "MATCH p=(a:Entity)-[rels:TDM_REL" in call.query]
    assert len(path_calls) == 1
    assert path_calls[0].params.get("rel_types") == ["USES_TABLE", "HAS_COLUMN"]


def test_clear_all_edges_removes_core_and_tdm_relationships() -> None:
    """Reset should clear both RELATES_TO and TDM_REL relationships."""
    session = _FakeSession()
    store = GraphStore()
    store.is_enabled = lambda: True
    store._get_driver = lambda: _FakeDriver(session)

    deleted = store.clear_all_edges()

    assert deleted == 3
    delete_calls = [call for call in session.calls if "DELETE r" in call.query]
    assert len(delete_calls) == 1
    assert "RELATES_TO|TDM_REL" in delete_calls[0].query
    node_calls = [call for call in session.calls if "DELETE n" in call.query]
    assert len(node_calls) == 1
