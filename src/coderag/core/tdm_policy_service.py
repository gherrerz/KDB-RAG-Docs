"""TDM guardrail policy service extracted from runtime facade."""

from __future__ import annotations

from collections.abc import Callable

from coderag.core.settings import Settings


class TdmPolicyService:
    """Own feature-gate and runtime capability checks for TDM flows."""

    def __init__(
        self,
        *,
        settings: Settings,
        is_graph_enabled: Callable[[], bool],
    ) -> None:
        """Build TDM policy service from settings and graph capability."""
        self._settings = settings
        self._is_graph_enabled = is_graph_enabled

    def is_tdm_graph_enabled(self) -> bool:
        """Return whether TDM can run with graph-backed capabilities."""
        return bool(self._settings.enable_tdm and self._is_graph_enabled())

    def ensure_tdm_enabled(self) -> None:
        """Require explicit TDM feature flag for additive endpoints."""
        if not self._settings.enable_tdm:
            raise RuntimeError(
                "TDM endpoints are disabled. Set ENABLE_TDM=true to enable."
            )

    def ensure_tdm_graph_enabled(self) -> None:
        """Require TDM flag plus Neo4j graph runtime availability."""
        self.ensure_tdm_enabled()
        if not self._is_graph_enabled():
            raise RuntimeError(
                "TDM is unavailable because USE_NEO4J=false. "
                "Enable Neo4j graph runtime to use TDM endpoints."
            )