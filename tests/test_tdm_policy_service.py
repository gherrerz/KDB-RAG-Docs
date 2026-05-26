"""Unit tests for TdmPolicyService guardrails."""

from __future__ import annotations

import pytest

from coderag.core.tdm_policy_service import TdmPolicyService


class _SettingsStub:
    """Minimal settings stub exposing ENABLE_TDM behavior."""

    def __init__(self, *, enable_tdm: bool) -> None:
        self.enable_tdm = enable_tdm


def test_is_tdm_graph_enabled_requires_feature_and_graph() -> None:
    """TDM graph should require both feature flag and graph capability."""
    enabled_graph_policy = TdmPolicyService(
        settings=_SettingsStub(enable_tdm=True),  # type: ignore[arg-type]
        is_graph_enabled=lambda: True,
    )
    disabled_flag_policy = TdmPolicyService(
        settings=_SettingsStub(enable_tdm=False),  # type: ignore[arg-type]
        is_graph_enabled=lambda: True,
    )
    disabled_graph_policy = TdmPolicyService(
        settings=_SettingsStub(enable_tdm=True),  # type: ignore[arg-type]
        is_graph_enabled=lambda: False,
    )

    assert enabled_graph_policy.is_tdm_graph_enabled() is True
    assert disabled_flag_policy.is_tdm_graph_enabled() is False
    assert disabled_graph_policy.is_tdm_graph_enabled() is False


def test_ensure_tdm_enabled_raises_when_flag_is_off() -> None:
    """Feature-gated TDM routes should fail fast when disabled."""
    policy = TdmPolicyService(
        settings=_SettingsStub(enable_tdm=False),  # type: ignore[arg-type]
        is_graph_enabled=lambda: True,
    )

    with pytest.raises(RuntimeError, match="TDM endpoints are disabled"):
        policy.ensure_tdm_enabled()


def test_ensure_tdm_graph_enabled_raises_when_graph_is_off() -> None:
    """TDM graph checks should fail when Neo4j runtime is unavailable."""
    policy = TdmPolicyService(
        settings=_SettingsStub(enable_tdm=True),  # type: ignore[arg-type]
        is_graph_enabled=lambda: False,
    )

    with pytest.raises(RuntimeError, match="USE_NEO4J=false"):
        policy.ensure_tdm_graph_enabled()