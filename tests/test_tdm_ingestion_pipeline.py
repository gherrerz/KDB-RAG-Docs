"""Integration tests for additive TDM ingestion workflow."""

from __future__ import annotations

from pathlib import Path

from coderag.core.models import SourceConfig
from coderag.ingestion.tdm_ingestion import ingest_tdm_assets
from coderag.storage.metadata_store import MetadataStore


def test_tdm_ingestion_populates_catalog_tables(tmp_path: Path) -> None:
    """Ingest SQL/OpenAPI/markdown assets into additive TDM store tables."""
    source_root = tmp_path / "tdm_source"
    source_root.mkdir(parents=True, exist_ok=True)

    (source_root / "schema.sql").write_text(
        """
        CREATE TABLE billing.invoices (
            invoice_id BIGINT NOT NULL,
            customer_email VARCHAR(255),
            total_amount DECIMAL(10,2)
        );
        """,
        encoding="utf-8",
    )
    (source_root / "openapi.json").write_text(
        """
        {
          "openapi": "3.0.0",
          "info": {"title": "billing-api"},
          "paths": {
            "/v1/invoices": {
              "get": {
                "operationId": "listInvoices",
                "x-table": "billing.invoices"
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )
    (source_root / "dictionary.md").write_text(
        """
        Tabla: billing.invoices
        Column: customer_email
        PII: email
        Masking: tokenize
        """,
        encoding="utf-8",
    )

    store = MetadataStore(tmp_path / "metadata.db")
    summary = ingest_tdm_assets(
        source=SourceConfig(
            source_type="tdm_folder",
            local_path=str(source_root),
        ),
        store=store,
    )

    assert summary["discovered_files"] >= 3
    assert summary["schemas"] >= 1
    assert summary["tables"] >= 1
    assert summary["columns"] >= 1
    assert summary["service_mappings"] >= 1
    assert summary["masking_rules"] >= 1

    assert len(store.list_tdm_schemas(source_id=summary["source_id"])) >= 1
    assert len(store.list_tdm_tables(source_id=summary["source_id"])) >= 1
    assert len(store.list_tdm_columns(source_id=summary["source_id"])) >= 1
    assert (
        len(store.list_tdm_service_mappings(source_id=summary["source_id"])) >= 1
    )
    assert len(store.list_tdm_masking_rules(source_id=summary["source_id"])) >= 1
