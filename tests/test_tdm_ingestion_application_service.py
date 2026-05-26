"""Unit tests for TdmIngestionApplicationService extraction."""

from __future__ import annotations

import pytest

from coderag.core import tdm_ingestion_service as tdm_ingest_module
from coderag.core.models import IngestionRequest, SourceConfig
from coderag.core.tdm_ingestion_service import TdmIngestionApplicationService


class _StoreStub:
    """Store stub exposing only TDM catalog list methods."""

    def list_tdm_schemas(self, source_id: str | None = None):  # type: ignore[no-untyped-def]
        _ = source_id
        return [{"schema_id": "sch-1", "schema_name": "billing"}]

    def list_tdm_tables(self, source_id: str | None = None):  # type: ignore[no-untyped-def]
        _ = source_id
        return [{"table_id": "tbl-1", "table_name": "invoices"}]

    def list_tdm_columns(self, source_id: str | None = None):  # type: ignore[no-untyped-def]
        _ = source_id
        return [{"column_id": "col-1", "table_id": "tbl-1"}]

    def list_tdm_service_mappings(  # type: ignore[no-untyped-def]
        self,
        source_id: str | None = None,
    ):
        _ = source_id
        return [{"mapping_id": "map-1", "table_id": "tbl-1"}]

    def list_tdm_masking_rules(self, source_id: str | None = None):  # type: ignore[no-untyped-def]
        _ = source_id
        return [{"rule_id": "rule-1", "column_id": "col-1"}]


class _GraphStoreStub:
    """Graph store stub that records replace_tdm_edges invocations."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def replace_tdm_edges(self, *, source_id: str, typed_edges):  # type: ignore[no-untyped-def]
        self.calls.append(
            {
                "source_id": source_id,
                "typed_edges": list(typed_edges),
            }
        )
        return {"batches_written": 2}


def _build_service() -> tuple[
    TdmIngestionApplicationService,
    dict[str, int],
    _GraphStoreStub,
]:
    """Create one service instance with guard call counter."""
    ensure_calls = {"count": 0}

    def _ensure() -> None:
        ensure_calls["count"] += 1

    graph_store = _GraphStoreStub()
    service = TdmIngestionApplicationService(
        store=_StoreStub(),  # type: ignore[arg-type]
        graph_store=graph_store,  # type: ignore[arg-type]
        ensure_tdm_graph_enabled=_ensure,
    )
    return service, ensure_calls, graph_store


def test_ingest_tdm_assets_syncs_typed_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ingestion should build and persist typed TDM edges for one source."""
    service, ensure_calls, graph_store = _build_service()

    monkeypatch.setattr(
        tdm_ingest_module,
        "ingest_tdm_assets",
        lambda **_kwargs: {
            "source_id": "src-1",
            "discovered_files": 3,
        },
    )
    monkeypatch.setattr(
        tdm_ingest_module,
        "build_tdm_typed_edges",
        lambda **_kwargs: [("a", "Entity", "TDM_REL", "b")],
    )

    result = service.ingest_tdm_assets(
        IngestionRequest(
            source=SourceConfig(
                source_type="tdm_folder",
                local_path="sample_data",
            )
        )
    )

    assert ensure_calls["count"] == 1
    assert result["status"] == "completed"
    assert result["source_id"] == "src-1"
    assert result["tdm_graph_edges"] == 1
    assert result["tdm_graph_batches"] == 2
    assert len(graph_store.calls) == 1
    assert graph_store.calls[0]["source_id"] == "src-1"


def test_ingest_tdm_assets_skips_graph_sync_without_source_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ingestion should skip graph recomputation when source_id is missing."""
    service, ensure_calls, graph_store = _build_service()

    monkeypatch.setattr(
        tdm_ingest_module,
        "ingest_tdm_assets",
        lambda **_kwargs: {
            "source_id": "",
            "discovered_files": 1,
        },
    )

    def _unexpected_build(**_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("build_tdm_typed_edges should not be called")

    monkeypatch.setattr(
        tdm_ingest_module,
        "build_tdm_typed_edges",
        _unexpected_build,
    )

    result = service.ingest_tdm_assets(
        IngestionRequest(
            source=SourceConfig(
                source_type="tdm_folder",
                local_path="sample_data",
            )
        )
    )

    assert ensure_calls["count"] == 1
    assert result["status"] == "completed"
    assert result["source_id"] == ""
    assert "tdm_graph_edges" not in result
    assert graph_store.calls == []