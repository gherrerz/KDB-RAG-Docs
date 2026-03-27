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

    def __init__(self, fail_unwind_calls: int = 0) -> None:
        self.calls: List[_Call] = []
        self.fail_unwind_calls = fail_unwind_calls

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type, exc, tb

    def run(self, query: str, **params: Any) -> None:
        self.calls.append(_Call(query=query, params=params))
        if "UNWIND" in query and self.fail_unwind_calls > 0:
            self.fail_unwind_calls -= 1
            raise OSError("transient Neo4j network hiccup")

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


def test_replace_edges_batches_unwind_writes() -> None:
    """Split large edge sets into multiple UNWIND writes by batch size."""
    session = _FakeSession()
    driver = _FakeDriver(session)
    store = GraphStore()
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
    finally:
        SETTINGS.neo4j_ingest_batch_size = original_batch
        SETTINGS.neo4j_ingest_max_retries = original_retries


def test_replace_edges_retries_transient_batch_failure() -> None:
    """Retry one failed UNWIND batch and eventually succeed."""
    session = _FakeSession(fail_unwind_calls=1)
    driver = _FakeDriver(session)
    store = GraphStore()
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
    finally:
        SETTINGS.neo4j_ingest_batch_size = original_batch
        SETTINGS.neo4j_ingest_max_retries = original_retries
        SETTINGS.neo4j_ingest_retry_delay_ms = original_delay
