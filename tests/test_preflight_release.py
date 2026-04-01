"""Tests for release preflight contract checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_preflight_module():
    """Load scripts/preflight_release.py as a module for testing."""
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "scripts" / "preflight_release.py"
    spec = importlib.util.spec_from_file_location(
        "preflight_release",
        module_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["preflight_release"] = module
    spec.loader.exec_module(module)
    return module


def test_evaluate_openapi_paths_accepts_complete_legacy_set() -> None:
    """Pass when all legacy paths are present and TDM is optional."""
    mod = _load_preflight_module()
    discovered = set(mod.LEGACY_PATHS)

    results = mod.evaluate_openapi_paths(
        discovered_paths=discovered,
        expect_tdm_enabled=False,
    )

    legacy = [result for result in results if result.name == "openapi:legacy_paths"][0]
    assert legacy.passed is True


def test_evaluate_openapi_paths_requires_tdm_when_expected() -> None:
    """Fail when TDM paths are expected but absent."""
    mod = _load_preflight_module()
    discovered = set(mod.LEGACY_PATHS)

    results = mod.evaluate_openapi_paths(
        discovered_paths=discovered,
        expect_tdm_enabled=True,
    )

    tdm = [result for result in results if result.name == "openapi:tdm_paths"][0]
    assert tdm.passed is False


def test_flag_checks_detect_invalid_dependency(monkeypatch) -> None:
    """Detect invalid combinations where sub-capabilities enable without base."""
    mod = _load_preflight_module()
    monkeypatch.setenv("ENABLE_TDM", "false")
    monkeypatch.setenv("TDM_ENABLE_SYNTHETIC", "true")

    results = mod._flag_checks()
    dependency = [result for result in results if result.name == "flags:dependency"][0]
    assert dependency.passed is False
