"""Unit tests for IngestionPresenter and formatter extraction."""

from __future__ import annotations

from coderag.ui.ingestion_formatters import format_async_readiness, status_to_badge
from coderag.ui.ingestion_presenter import IngestionPresenter


def test_ingestion_presenter_validates_folder_local_path() -> None:
    """Reject folder source when local path is missing."""
    presenter = IngestionPresenter()

    error, invalid = presenter.validate_inputs(
        source_type="folder",
        ingestion_channel="json_folder",
        local_path="   ",
        base_url="",
        token="",
        filters_raw="{}",
    )

    assert error == "La ruta local es obligatoria cuando el tipo es folder."
    assert invalid == {"local_path"}


def test_ingestion_presenter_build_payload_normalizes_fields() -> None:
    """Build payload with normalized source and deduplicated tags."""
    presenter = IngestionPresenter()

    payload = presenter.build_payload(
        source_type="folder",
        local_path="sample_data",
        base_url="",
        token="",
        filters_raw='{"space": "ENG"}',
        tags_raw="finance, urgent, finance",
        ingestion_channel="upload_file",
        execution_mode="async",
    )

    source = payload["source"]
    assert isinstance(source, dict)
    assert source["local_path"] == "sample_data"
    assert source["filters"] == {"space": "ENG"}
    assert source["tags"] == ["finance", "urgent"]
    assert payload["_ingestion_channel"] == "upload_file"


def test_ingestion_formatters_expose_readiness_and_badge_mapping() -> None:
    """Render readiness summary and map backend status to badge tokens."""
    rendered = format_async_readiness(
        {
            "ready": False,
            "recommendation": "sync",
            "checks": {"redis": {"required": True, "ok": False, "detail": "connection refused"}},
        }
    )

    assert "recommendation: sync" in rendered
    assert status_to_badge("finished") == "success"
