"""Unit tests for TdmPresenter extraction."""

from __future__ import annotations

from coderag.ui.tdm_presenter import TdmPresenter


def test_tdm_presenter_builds_virtualization_payload() -> None:
    """Build virtualization payload with optional field normalization."""
    presenter = TdmPresenter()

    payload = presenter.build_virtualization_preview_payload(
        question="",
        source_id="src-1",
        service_name="billing-api",
        table_name="invoices",
    )

    assert payload["question"] == "virtualization preview"
    assert payload["source_id"] == "src-1"
    assert payload["include_virtualization_preview"] is True


def test_tdm_presenter_extracts_rows_for_findings_and_plan() -> None:
    """Normalize findings and synthetic plan into table rows."""
    rows = TdmPresenter.extract_result_rows(
        {
            "findings": [
                {
                    "service_name": "billing-api",
                    "endpoint": "/v1/invoices",
                    "method": "GET",
                }
            ],
            "plan": {
                "table_name": "invoices",
                "target_rows": 1000,
                "strategy": "masking",
            },
        }
    )

    assert rows[0]["type"] == "finding"
    assert any(row["type"] == "synthetic_plan" for row in rows)


def test_tdm_presenter_maps_error_hints() -> None:
    """Map known backend detail strings to actionable UI hints."""
    hint = TdmPresenter.hint_for_error_detail("TDM endpoints are disabled.")
    assert "deshabilitado" in hint.lower()
