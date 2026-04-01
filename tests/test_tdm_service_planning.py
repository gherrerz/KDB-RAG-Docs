"""Service-level tests for TDM synthetic and virtualization planning."""

from __future__ import annotations

from coderag.core.models import TdmQueryRequest
from coderag.core.service import SERVICE
from coderag.core.settings import SETTINGS


def test_preview_virtualization_requires_feature_flag() -> None:
    """Reject virtualization preview when capability flag is disabled."""
    original_enable_tdm = SETTINGS.enable_tdm
    original_enable_virtualization = SETTINGS.tdm_enable_virtualization
    try:
        SETTINGS.enable_tdm = True
        SETTINGS.tdm_enable_virtualization = False
        request = TdmQueryRequest(question="virtualizacion", source_id="src-1")
        try:
            SERVICE.preview_tdm_virtualization(request)
            assert False, "Expected RuntimeError when virtualization flag is off"
        except RuntimeError:
            pass
    finally:
        SETTINGS.enable_tdm = original_enable_tdm
        SETTINGS.tdm_enable_virtualization = original_enable_virtualization


def test_get_tdm_synthetic_profile_requires_feature_flag() -> None:
    """Reject synthetic profile generation when capability flag is disabled."""
    original_enable_tdm = SETTINGS.enable_tdm
    original_enable_synthetic = SETTINGS.tdm_enable_synthetic
    try:
        SETTINGS.enable_tdm = True
        SETTINGS.tdm_enable_synthetic = False
        try:
            SERVICE.get_tdm_synthetic_profile(table_name="invoices")
            assert False, "Expected RuntimeError when synthetic flag is off"
        except RuntimeError:
            pass
    finally:
        SETTINGS.enable_tdm = original_enable_tdm
        SETTINGS.tdm_enable_synthetic = original_enable_synthetic
