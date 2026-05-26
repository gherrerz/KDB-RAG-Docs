"""Unit tests for TdmQueryApplicationService extracted TDM logic."""

from __future__ import annotations

import pytest

from coderag.core import tdm_query_service as tdm_module
from coderag.core.models import TdmQueryRequest
from coderag.core.tdm_query_service import TdmQueryApplicationService


class _SettingsStub:
    """Minimal settings collaborator for TDM query service tests."""

    def __init__(
        self,
        *,
        masking: bool = True,
        synthetic: bool = True,
        virtualization: bool = True,
    ) -> None:
        self.tdm_enable_masking = masking
        self.tdm_enable_synthetic = synthetic
        self.tdm_enable_virtualization = virtualization


class _StoreStub:
    """Store stub with configurable TDM catalog rows and upsert capture."""

    def __init__(self) -> None:
        self.tables = [
            {"table_id": "tbl-1", "table_name": "invoices"},
            {"table_id": "tbl-2", "table_name": "customers"},
        ]
        self.columns = [
            {"column_id": "col-1", "table_id": "tbl-1", "column_name": "card_pan"},
            {"column_id": "col-2", "table_id": "tbl-2", "column_name": "name"},
        ]
        self.mappings = [
            {
                "mapping_id": "map-1",
                "service_name": "BillingService",
                "table_id": "tbl-1",
            },
            {
                "mapping_id": "map-2",
                "service_name": "CustomerService",
                "table_id": "tbl-2",
            },
        ]
        self.masking_rules = [
            {
                "rule_id": "rule-1",
                "column_id": "col-1",
                "policy_type": "mask",
            }
        ]
        self.virtualization_upserts: list[dict[str, object]] = []
        self.synthetic_upserts: list[dict[str, object]] = []

    def list_tdm_tables(self, source_id: str | None = None) -> list[dict[str, object]]:
        _ = source_id
        return list(self.tables)

    def list_tdm_columns(self, source_id: str | None = None) -> list[dict[str, object]]:
        _ = source_id
        return list(self.columns)

    def list_tdm_service_mappings(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, object]]:
        _ = source_id
        return list(self.mappings)

    def list_tdm_masking_rules(
        self,
        source_id: str | None = None,
    ) -> list[dict[str, object]]:
        _ = source_id
        return list(self.masking_rules)

    def upsert_tdm_virtualization_artifact(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.virtualization_upserts.append(kwargs)

    def upsert_tdm_synthetic_profile(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.synthetic_upserts.append(kwargs)


class _GraphStoreStub:
    """Graph stub exposing only expand_tdm_paths used by the service."""

    def expand_tdm_paths(self, **_kwargs):  # type: ignore[no-untyped-def]
        return [{"nodes": ["billing", "invoices"], "relationships": ["USES"]}]


def _build_service(
    *,
    settings: _SettingsStub,
    store: _StoreStub | None = None,
) -> tuple[TdmQueryApplicationService, dict[str, int], _StoreStub]:
    """Create one TDM query service with ensure callback call counter."""
    ensure_calls = {"count": 0}

    def _ensure() -> None:
        ensure_calls["count"] += 1

    active_store = store or _StoreStub()
    service = TdmQueryApplicationService(
        store=active_store,  # type: ignore[arg-type]
        graph_store=_GraphStoreStub(),  # type: ignore[arg-type]
        settings=settings,  # type: ignore[arg-type]
        ensure_tdm_graph_enabled=_ensure,
    )
    return service, ensure_calls, active_store


def test_query_tdm_filters_catalog_and_applies_masking_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Query should filter findings and attach masking preview when enabled."""
    service, ensure_calls, _store = _build_service(settings=_SettingsStub(masking=True))

    monkeypatch.setattr(
        tdm_module,
        "apply_masking_rules_to_row",
        lambda **_kwargs: {"card_pan": "****"},
    )

    response = service.query_tdm(
        TdmQueryRequest(
            question="masking for invoices",
            table_name="invoices",
            source_id="src-1",
        )
    )

    assert ensure_calls["count"] == 1
    assert response.diagnostics["table_filter"] == "invoices"
    assert response.diagnostics["masking_enabled"] is True
    assert response.diagnostics["graph_paths"] == 1
    assert any("masking_preview" in finding for finding in response.findings)


def test_query_tdm_falls_back_to_first_ten_mappings() -> None:
    """When no filters match, query should return first ten service mappings."""
    store = _StoreStub()
    store.mappings = [
        {
            "mapping_id": f"map-{idx}",
            "service_name": f"Service{idx}",
            "table_id": "tbl-2",
        }
        for idx in range(12)
    ]
    service, _ensure_calls, _store = _build_service(
        settings=_SettingsStub(masking=False),
        store=store,
    )

    response = service.query_tdm(
        TdmQueryRequest(
            question="unknown",
            service_name="MissingService",
            source_id="src-1",
        )
    )

    assert len(response.findings) == 10
    assert response.findings[0]["mapping_id"] == "map-0"


def test_get_tdm_service_catalog_filters_service_name() -> None:
    """Service catalog should return only mappings for one service."""
    service, ensure_calls, _store = _build_service(settings=_SettingsStub())

    result = service.get_tdm_service_catalog(
        service_name="BillingService",
        source_id="src-1",
    )

    assert ensure_calls["count"] == 1
    assert result["service_name"] == "BillingService"
    assert result["count"] == 1
    assert result["mappings"][0]["mapping_id"] == "map-1"


def test_get_tdm_table_catalog_filters_columns_by_table_name() -> None:
    """Table catalog should include matched table and its columns only."""
    service, ensure_calls, _store = _build_service(settings=_SettingsStub())

    result = service.get_tdm_table_catalog(
        table_name="invoices",
        source_id="src-1",
    )

    assert ensure_calls["count"] == 1
    assert result["table_name"] == "invoices"
    assert result["count"] == 1
    assert len(result["tables"]) == 1
    assert result["tables"][0]["table_id"] == "tbl-1"
    assert len(result["columns"]) == 1
    assert result["columns"][0]["column_id"] == "col-1"


def test_preview_virtualization_requires_feature_flag() -> None:
    """Preview virtualization should fail fast when feature flag is disabled."""
    service, _ensure_calls, _store = _build_service(
        settings=_SettingsStub(virtualization=False)
    )

    with pytest.raises(RuntimeError, match="TDM virtualization is disabled"):
        service.preview_tdm_virtualization(TdmQueryRequest(question="preview"))


def test_preview_virtualization_persists_generated_templates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preview virtualization should upsert every generated template."""
    service, _ensure_calls, store = _build_service(
        settings=_SettingsStub(virtualization=True)
    )

    monkeypatch.setattr(
        tdm_module,
        "build_virtualization_templates",
        lambda **_kwargs: [
            {
                "artifact_id": "art-1",
                "service_name": "BillingService",
                "artifact_type": "wiremock",
                "content": {"stub": 1},
                "metadata": {"version": 1},
            },
            {
                "artifact_id": "art-2",
                "service_name": "BillingService",
                "artifact_type": "wiremock",
                "content": {"stub": 2},
                "metadata": {"version": 1},
            },
        ],
    )

    response = service.preview_tdm_virtualization(
        TdmQueryRequest(
            question="preview",
            source_id="src-1",
            service_name="BillingService",
        )
    )

    assert response["count"] == 2
    assert len(store.virtualization_upserts) == 2
    assert store.virtualization_upserts[0]["artifact_id"] == "art-1"


def test_get_tdm_synthetic_profile_requires_feature_flag() -> None:
    """Synthetic profile generation should fail fast when feature is disabled."""
    service, _ensure_calls, _store = _build_service(
        settings=_SettingsStub(synthetic=False)
    )

    with pytest.raises(RuntimeError, match="TDM synthetic planning is disabled"):
        service.get_tdm_synthetic_profile(table_name="invoices")


def test_get_tdm_synthetic_profile_persists_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Synthetic profile generation should persist profile metadata in store."""
    service, _ensure_calls, store = _build_service(settings=_SettingsStub())

    monkeypatch.setattr(
        tdm_module,
        "build_synthetic_profile_plan",
        lambda **_kwargs: {"rows": 500, "strategy": "template"},
    )

    result = service.get_tdm_synthetic_profile(
        table_name="invoices",
        source_id="src-1",
        target_rows=500,
    )

    assert result["profile_id"] == "syn-invoices-500"
    assert result["plan"]["rows"] == 500
    assert len(store.synthetic_upserts) == 1
    assert store.synthetic_upserts[0]["target_table_id"] == "tbl-1"