"""API tests for additive TDM endpoints and compatibility gating."""

from __future__ import annotations

from fastapi.testclient import TestClient

from coderag.api import server


def test_tdm_endpoints_return_404_when_feature_disabled() -> None:
    """Keep TDM routes unavailable unless ENABLE_TDM is explicitly enabled."""
    client = TestClient(server.app)
    original_enable_tdm = server.SETTINGS.enable_tdm
    server.SETTINGS.enable_tdm = False
    try:
        response = client.post(
            "/tdm/query",
            json={"question": "impacto de billing", "source_id": None},
        )
        assert response.status_code == 404

        ingest_response = client.post(
            "/tdm/ingest",
            json={
                "source": {
                    "source_type": "tdm_folder",
                    "local_path": "sample_data",
                    "filters": {},
                }
            },
        )
        assert ingest_response.status_code == 404
    finally:
        server.SETTINGS.enable_tdm = original_enable_tdm


def test_tdm_endpoints_delegate_to_service_when_enabled() -> None:
    """Expose additive TDM endpoints while preserving legacy routes."""
    client = TestClient(server.app)
    original_enable_tdm = server.SETTINGS.enable_tdm
    original_use_neo4j = server.SETTINGS.use_neo4j
    original_query_tdm = server.SERVICE.query_tdm
    original_ingest_tdm = server.SERVICE.ingest_tdm_assets
    original_get_service_catalog = server.SERVICE.get_tdm_service_catalog
    original_get_table_catalog = server.SERVICE.get_tdm_table_catalog
    original_preview = server.SERVICE.preview_tdm_virtualization
    original_get_synthetic = server.SERVICE.get_tdm_synthetic_profile

    server.SETTINGS.enable_tdm = True
    server.SETTINGS.use_neo4j = True
    server.SERVICE.query_tdm = lambda request: type(
        "_Resp",
        (),
        {
            "model_dump": lambda self: {
                "answer": "ok",
                "findings": [],
                "diagnostics": {"mode": "tdm"},
            }
        },
    )()
    server.SERVICE.ingest_tdm_assets = lambda request: {
        "status": "completed",
        "source_id": "src-1",
    }
    server.SERVICE.get_tdm_service_catalog = (
        lambda service_name, source_id=None: {
            "service_name": service_name,
            "source_id": source_id,
            "mappings": [],
            "count": 0,
        }
    )
    server.SERVICE.get_tdm_table_catalog = (
        lambda table_name, source_id=None: {
            "table_name": table_name,
            "source_id": source_id,
            "tables": [],
            "columns": [],
            "count": 0,
        }
    )
    server.SERVICE.preview_tdm_virtualization = lambda request: {
        "templates": [],
        "count": 0,
    }
    server.SERVICE.get_tdm_synthetic_profile = (
        lambda table_name, source_id=None, target_rows=1000: {
            "table_name": table_name,
            "source_id": source_id,
            "profile_id": "syn-1",
            "plan": {"target_rows": target_rows},
        }
    )

    try:
        query_response = client.post(
            "/tdm/query",
            json={"question": "impacto de billing", "source_id": None},
        )
        assert query_response.status_code == 200
        assert query_response.json().get("diagnostics", {}).get("mode") == "tdm"

        ingest_response = client.post(
            "/tdm/ingest",
            json={
                "source": {
                    "source_type": "tdm_folder",
                    "local_path": "sample_data",
                    "filters": {},
                }
            },
        )
        assert ingest_response.status_code == 200
        assert ingest_response.json().get("status") == "completed"

        service_catalog = client.get("/tdm/catalog/services/billing-api")
        assert service_catalog.status_code == 200

        table_catalog = client.get("/tdm/catalog/tables/invoices")
        assert table_catalog.status_code == 200

        preview = client.post(
            "/tdm/virtualization/preview",
            json={"question": "virtualizar billing", "service_name": "billing-api"},
        )
        assert preview.status_code == 200

        synthetic = client.get("/tdm/synthetic/profile/invoices?target_rows=200")
        assert synthetic.status_code == 200
        assert synthetic.json().get("profile_id") == "syn-1"
    finally:
        server.SETTINGS.enable_tdm = original_enable_tdm
        server.SETTINGS.use_neo4j = original_use_neo4j
        server.SERVICE.query_tdm = original_query_tdm
        server.SERVICE.ingest_tdm_assets = original_ingest_tdm
        server.SERVICE.get_tdm_service_catalog = original_get_service_catalog
        server.SERVICE.get_tdm_table_catalog = original_get_table_catalog
        server.SERVICE.preview_tdm_virtualization = original_preview
        server.SERVICE.get_tdm_synthetic_profile = original_get_synthetic


def test_tdm_endpoints_return_degraded_200_when_neo4j_disabled() -> None:
    """Return stable disabled payloads when TDM is on but Neo4j is off."""
    client = TestClient(server.app)
    original_enable_tdm = server.SETTINGS.enable_tdm
    original_use_neo4j = server.SETTINGS.use_neo4j

    server.SETTINGS.enable_tdm = True
    server.SETTINGS.use_neo4j = False

    try:
        query_response = client.post(
            "/tdm/query",
            json={"question": "impacto de billing", "source_id": None},
        )
        assert query_response.status_code == 200
        query_body = query_response.json()
        assert query_body["findings"] == []
        assert query_body["diagnostics"]["status"] == "disabled"
        assert query_body["diagnostics"]["neo4j_enabled"] is False

        ingest_response = client.post(
            "/tdm/ingest",
            json={
                "source": {
                    "source_type": "tdm_folder",
                    "local_path": "sample_data",
                    "filters": {},
                }
            },
        )
        assert ingest_response.status_code == 200
        assert ingest_response.json()["status"] == "disabled"

        service_catalog = client.get("/tdm/catalog/services/billing-api")
        assert service_catalog.status_code == 200
        assert service_catalog.json()["count"] == 0

        table_catalog = client.get("/tdm/catalog/tables/invoices")
        assert table_catalog.status_code == 200
        assert table_catalog.json()["count"] == 0

        preview = client.post(
            "/tdm/virtualization/preview",
            json={"question": "virtualizar billing", "service_name": "billing-api"},
        )
        assert preview.status_code == 200
        assert preview.json()["count"] == 0

        synthetic = client.get("/tdm/synthetic/profile/invoices?target_rows=200")
        assert synthetic.status_code == 200
        assert synthetic.json()["profile_id"] is None
        assert synthetic.json()["diagnostics"]["status"] == "disabled"
    finally:
        server.SETTINGS.enable_tdm = original_enable_tdm
        server.SETTINGS.use_neo4j = original_use_neo4j
