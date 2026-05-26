"""Contract tests for the transitional hybrid metadata store."""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("sqlalchemy")

from coderag.storage import hybrid_metadata_store as hybrid_module


class _FakeSqliteStore:
    """Minimal SQLite stand-in for hybrid routing tests."""

    def clear_all_data(self) -> dict[str, int]:
        """Return deterministic cleanup counters from the legacy backend."""
        return {
            "deleted_documents": 1,
            "deleted_chunks": 2,
            "deleted_graph_edges": 4,
            "deleted_jobs": 5,
        }

    def legacy_passthrough(self, value: str) -> str:
        """Expose one unported method to verify `__getattr__` delegation."""
        return f"sqlite:{value}"


class _FakeDocumentStore:
    """Capture document routing calls without touching PostgreSQL."""

    last_instance: "_FakeDocumentStore | None" = None

    def __init__(self, postgres_dsn: str) -> None:
        """Remember the instance so tests can inspect recorded calls."""
        self.postgres_dsn = postgres_dsn
        self.calls: list[tuple[str, Any]] = []
        type(self).last_instance = self

    def list_tag_facets(
        self,
        source_id: str | None = None,
    ) -> list[tuple[str, int]]:
        """Return deterministic tag facets for routing verification."""
        self.calls.append(("list_tag_facets", source_id))
        return [("alpha", 2), ("beta", 1)]

    def clear_document_data(self) -> dict[str, int]:
        """Return deterministic cleanup counters from Postgres."""
        self.calls.append(("clear_document_data", None))
        return {
            "deleted_documents": 3,
            "deleted_chunks": 7,
            "deleted_graph_edges": 13,
        }

    def replace_graph_edges(
        self,
        source_id: str,
        edges: list[tuple[str, str, str, str, str]],
    ) -> None:
        """Record graph edge replacement calls for routing verification."""
        self.calls.append(("replace_graph_edges", source_id, list(edges)))

    def list_graph_edges(
        self,
        source_id: str | None = None,
    ) -> list[tuple[str, str, str]]:
        """Return deterministic graph edges for routing verification."""
        self.calls.append(("list_graph_edges", source_id))
        return [("service", "calls", "database")]


class _FakeJobStore:
    """Capture job cleanup routing without touching PostgreSQL."""

    last_instance: "_FakeJobStore | None" = None

    def __init__(self, postgres_dsn: str) -> None:
        """Remember the instance so tests can inspect recorded calls."""
        self.postgres_dsn = postgres_dsn
        self.calls: list[str] = []
        type(self).last_instance = self

    def clear_jobs(self) -> int:
        """Return deterministic cleanup count for job rows."""
        self.calls.append("clear_jobs")
        return 11


class _FakeTdmStore:
    """Capture TDM routing calls without touching PostgreSQL."""

    last_instance: "_FakeTdmStore | None" = None

    def __init__(self, postgres_dsn: str) -> None:
        """Remember the instance so tests can inspect recorded calls."""
        self.postgres_dsn = postgres_dsn
        self.calls: list[Any] = []
        type(self).last_instance = self

    def list_tdm_tables(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return deterministic TDM tables for routing verification."""
        self.calls.append(("list_tdm_tables", source_id))
        return [
            {
                "table_id": "table-1",
                "source_id": source_id,
                "schema_id": "schema-1",
                "table_name": "customers",
                "table_type": "table",
                "metadata": {},
            }
        ]

    def upsert_tdm_virtualization_artifact(
        self,
        artifact_id: str,
        source_id: str,
        service_name: str,
        artifact_type: str,
        content: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record virtualization artifact writes for routing verification."""
        self.calls.append(
            (
                "upsert_tdm_virtualization_artifact",
                artifact_id,
                source_id,
                service_name,
                artifact_type,
                dict(content or {}),
                dict(metadata or {}),
            )
        )

    def clear_tdm_data(self) -> dict[str, int]:
        """Return deterministic cleanup counters from Postgres TDM tables."""
        self.calls.append(("clear_tdm_data", None))
        return {"deleted_tdm_tables": 1}


def test_list_unique_tags_routes_to_postgres_document_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hybrid tag listing must use the Postgres-backed document slice."""
    monkeypatch.setattr(
        hybrid_module,
        "PostgresDocumentChunkStore",
        _FakeDocumentStore,
    )
    monkeypatch.setattr(
        hybrid_module,
        "PostgresJobStateStore",
        _FakeJobStore,
    )
    monkeypatch.setattr(
        hybrid_module,
        "PostgresTdmStore",
        _FakeTdmStore,
    )

    store = hybrid_module.HybridMetadataStore(
        sqlite_store=_FakeSqliteStore(),
        postgres_dsn="postgresql://docs:secret@db.local/docs",
    )

    tags = store.list_unique_tags(source_id="src-1")

    assert tags == ["alpha", "beta"]
    assert _FakeDocumentStore.last_instance is not None
    assert _FakeDocumentStore.last_instance.calls == [
        ("list_tag_facets", "src-1")
    ]


def test_clear_all_data_sums_sqlite_and_postgres_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hybrid cleanup must aggregate legacy and Postgres-managed counters."""
    monkeypatch.setattr(
        hybrid_module,
        "PostgresDocumentChunkStore",
        _FakeDocumentStore,
    )
    monkeypatch.setattr(
        hybrid_module,
        "PostgresJobStateStore",
        _FakeJobStore,
    )
    monkeypatch.setattr(
        hybrid_module,
        "PostgresTdmStore",
        _FakeTdmStore,
    )

    store = hybrid_module.HybridMetadataStore(
        sqlite_store=_FakeSqliteStore(),
        postgres_dsn="postgresql://docs:secret@db.local/docs",
    )

    deleted = store.clear_all_data()

    assert deleted == {
        "deleted_documents": 4,
        "deleted_chunks": 9,
        "deleted_graph_edges": 17,
        "deleted_jobs": 16,
    }
    assert _FakeDocumentStore.last_instance is not None
    assert _FakeDocumentStore.last_instance.calls == [
        ("clear_document_data", None)
    ]
    assert _FakeTdmStore.last_instance is not None
    assert _FakeTdmStore.last_instance.calls == [("clear_tdm_data", None)]
    assert _FakeJobStore.last_instance is not None
    assert _FakeJobStore.last_instance.calls == ["clear_jobs"]


def test_graph_edge_calls_route_to_postgres_document_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hybrid graph methods must use the Postgres-backed document slice."""
    monkeypatch.setattr(
        hybrid_module,
        "PostgresDocumentChunkStore",
        _FakeDocumentStore,
    )
    monkeypatch.setattr(
        hybrid_module,
        "PostgresJobStateStore",
        _FakeJobStore,
    )
    monkeypatch.setattr(
        hybrid_module,
        "PostgresTdmStore",
        _FakeTdmStore,
    )

    store = hybrid_module.HybridMetadataStore(
        sqlite_store=_FakeSqliteStore(),
        postgres_dsn="postgresql://docs:secret@db.local/docs",
    )
    edges = [("edge-1", "src", "rel", "dst", "source-1")]

    store.replace_graph_edges(source_id="source-1", edges=edges)
    listed_edges = store.list_graph_edges(source_id="source-1")

    assert listed_edges == [("service", "calls", "database")]
    assert _FakeDocumentStore.last_instance is not None
    assert _FakeDocumentStore.last_instance.calls == [
        ("replace_graph_edges", "source-1", edges),
        ("list_graph_edges", "source-1"),
    ]


def test_tdm_calls_route_to_postgres_tdm_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hybrid TDM methods must use the Postgres-backed TDM slice."""
    monkeypatch.setattr(
        hybrid_module,
        "PostgresDocumentChunkStore",
        _FakeDocumentStore,
    )
    monkeypatch.setattr(
        hybrid_module,
        "PostgresJobStateStore",
        _FakeJobStore,
    )
    monkeypatch.setattr(
        hybrid_module,
        "PostgresTdmStore",
        _FakeTdmStore,
    )

    store = hybrid_module.HybridMetadataStore(
        sqlite_store=_FakeSqliteStore(),
        postgres_dsn="postgresql://docs:secret@db.local/docs",
    )

    tables = store.list_tdm_tables(source_id="src-1")
    store.upsert_tdm_virtualization_artifact(
        artifact_id="artifact-1",
        source_id="src-1",
        service_name="billing-api",
        artifact_type="mock-template",
        content={"endpoint": "/v1/customers"},
        metadata={"owner": "qa"},
    )

    assert tables[0]["table_id"] == "table-1"
    assert _FakeTdmStore.last_instance is not None
    assert _FakeTdmStore.last_instance.calls == [
        ("list_tdm_tables", "src-1"),
        (
            "upsert_tdm_virtualization_artifact",
            "artifact-1",
            "src-1",
            "billing-api",
            "mock-template",
            {"endpoint": "/v1/customers"},
            {"owner": "qa"},
        ),
    ]


def test_unported_methods_delegate_to_sqlite_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hybrid store should delegate unknown methods to legacy SQLite object."""
    monkeypatch.setattr(
        hybrid_module,
        "PostgresDocumentChunkStore",
        _FakeDocumentStore,
    )
    monkeypatch.setattr(
        hybrid_module,
        "PostgresJobStateStore",
        _FakeJobStore,
    )
    monkeypatch.setattr(
        hybrid_module,
        "PostgresTdmStore",
        _FakeTdmStore,
    )

    sqlite_store = _FakeSqliteStore()
    store = hybrid_module.HybridMetadataStore(
        sqlite_store=sqlite_store,
        postgres_dsn="postgresql://docs:secret@db.local/docs",
    )

    assert store.legacy_passthrough("ok") == "sqlite:ok"