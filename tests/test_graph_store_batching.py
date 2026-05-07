"""Tests for Neo4j batched relationship persistence behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from coderag.core.graph_store import GraphStore
from coderag.core.settings import SETTINGS


@dataclass
class _Call:
    """Simple record of a cypher call for assertions."""

    query: str
    params: Dict[str, Any]


class _FakeSession:
    """Minimal Neo4j-like session with execute_write support."""

    def __init__(
        self,
        fail_unwind_calls: int = 0,
        relationships_deleted: int = 0,
        nodes_deleted: int = 0,
    ) -> None:
        self.calls: List[_Call] = []
        self.fail_unwind_calls = fail_unwind_calls
        self.relationships_deleted = relationships_deleted
        self.nodes_deleted = nodes_deleted

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type, exc, tb

    def run(self, query: str, **params: Any):
        self.calls.append(_Call(query=query, params=params))
        if "UNWIND" in query and self.fail_unwind_calls > 0:
            self.fail_unwind_calls -= 1
            raise OSError("transient Neo4j network hiccup")
        if "DELETE n" in query:
            return _FakeResult(nodes_deleted=self.nodes_deleted)
        if "DELETE r" in query:
            return _FakeResult(
                relationships_deleted=self.relationships_deleted
            )
        return _FakeResult()

    def execute_write(self, fn, rows: List[Dict[str, str]]) -> None:
        fn(self, rows)


class _FakeDriver:
    """Minimal Neo4j-like driver wrapper for GraphStore tests."""

    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def session(self) -> _FakeSession:
        return self._session


def _edge(i: int) -> Tuple[str, str, str, str, str]:
    """Build deterministic edge tuple compatible with GraphStore."""
    return (f"e{i}", f"Node{i}", "RELATES_TO", f"Node{i+1}", "source-x")


class _Counters:
    """Minimal counters object used by fake result summaries."""

    def __init__(
        self,
        relationships_deleted: int = 0,
        nodes_deleted: int = 0,
    ) -> None:
        self.relationships_deleted = relationships_deleted
        self.nodes_deleted = nodes_deleted


class _Summary:
    """Minimal summary object for GraphStore cleanup tests."""

    def __init__(
        self,
        relationships_deleted: int = 0,
        nodes_deleted: int = 0,
    ) -> None:
        self.counters = _Counters(
            relationships_deleted=relationships_deleted,
            nodes_deleted=nodes_deleted,
        )


class _FakeResult:
    """Minimal result object that exposes consume()."""

    def __init__(
        self,
        relationships_deleted: int = 0,
        nodes_deleted: int = 0,
    ) -> None:
        self._relationships_deleted = relationships_deleted
        self._nodes_deleted = nodes_deleted

    def consume(self) -> _Summary:
        return _Summary(
            relationships_deleted=self._relationships_deleted,
            nodes_deleted=self._nodes_deleted,
        )


def test_replace_edges_batches_unwind_writes() -> None:
    """Split large edge sets into multiple UNWIND writes by batch size."""
    session = _FakeSession()
    driver = _FakeDriver(session)
    store = GraphStore()
    store.is_enabled = lambda: True
    store._get_driver = lambda: driver

    original_batch = SETTINGS.neo4j_ingest_batch_size
    original_retries = SETTINGS.neo4j_ingest_max_retries
    try:
        SETTINGS.neo4j_ingest_batch_size = 2
        SETTINGS.neo4j_ingest_max_retries = 0

        metrics = store.replace_edges(
            source_id="source-x",
            edges=[_edge(1), _edge(2), _edge(3), _edge(4), _edge(5)],
        )

        unwind_calls = [call for call in session.calls if "UNWIND" in call.query]
        assert len(unwind_calls) == 3
        assert metrics["batches_written"] == 3
        assert metrics["rows_written"] == 5
        assert metrics["retries"] == 0
        assert metrics["batch_size"] == 2
        assert metrics["nodes_deleted"] == 0
    finally:
        SETTINGS.neo4j_ingest_batch_size = original_batch
        SETTINGS.neo4j_ingest_max_retries = original_retries


def test_replace_edges_retries_transient_batch_failure() -> None:
    """Retry one failed UNWIND batch and eventually succeed."""
    session = _FakeSession(fail_unwind_calls=1)
    driver = _FakeDriver(session)
    store = GraphStore()
    store.is_enabled = lambda: True
    store._get_driver = lambda: driver

    original_batch = SETTINGS.neo4j_ingest_batch_size
    original_retries = SETTINGS.neo4j_ingest_max_retries
    original_delay = SETTINGS.neo4j_ingest_retry_delay_ms
    try:
        SETTINGS.neo4j_ingest_batch_size = 10
        SETTINGS.neo4j_ingest_max_retries = 2
        SETTINGS.neo4j_ingest_retry_delay_ms = 1

        metrics = store.replace_edges(
            source_id="source-x",
            edges=[_edge(1), _edge(2), _edge(3)],
        )

        unwind_calls = [call for call in session.calls if "UNWIND" in call.query]
        assert len(unwind_calls) == 2
        assert metrics["batches_written"] == 1
        assert metrics["rows_written"] == 3
        assert metrics["retries"] == 1
        assert metrics["nodes_deleted"] == 0
    finally:
        SETTINGS.neo4j_ingest_batch_size = original_batch
        SETTINGS.neo4j_ingest_max_retries = original_retries
        SETTINGS.neo4j_ingest_retry_delay_ms = original_delay


def test_replace_edges_deletes_orphan_entities_after_resync() -> None:
    """Clean orphan Entity nodes after replacing one source edge set."""
    session = _FakeSession(nodes_deleted=2)
    driver = _FakeDriver(session)
    store = GraphStore()
    store.is_enabled = lambda: True
    store._get_driver = lambda: driver

    original_batch = SETTINGS.neo4j_ingest_batch_size
    original_retries = SETTINGS.neo4j_ingest_max_retries
    try:
        SETTINGS.neo4j_ingest_batch_size = 10
        SETTINGS.neo4j_ingest_max_retries = 0

        metrics = store.replace_edges(
            source_id="source-x",
            edges=[_edge(1), _edge(2)],
        )

        node_calls = [call for call in session.calls if "DELETE n" in call.query]
        assert len(node_calls) == 1
        assert metrics["nodes_deleted"] == 2
    finally:
        SETTINGS.neo4j_ingest_batch_size = original_batch
        SETTINGS.neo4j_ingest_max_retries = original_retries
