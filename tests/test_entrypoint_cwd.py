"""Regression tests for entrypoint CWD pinning."""

from __future__ import annotations

from pathlib import Path

import src.main as main
import src.run_ui as run_ui


def test_main_pins_cwd_to_repo_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Ensure API entrypoint helper resets CWD to repository root."""
    monkeypatch.chdir(tmp_path)
    main._ensure_repo_cwd()

    assert Path.cwd() == main._repo_root()


def test_main_resolves_default_bind_host_port(monkeypatch) -> None:
    """Default API entrypoint bind should stay compatible with 0.0.0.0:8000."""
    monkeypatch.delenv("API_HOST", raising=False)
    monkeypatch.delenv("API_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)

    host, port = main._resolve_bind_host_port()

    assert host == "0.0.0.0"
    assert port == 8000


def test_main_prefers_api_port_over_generic_port(monkeypatch) -> None:
    """API_PORT should override generic platform PORT when both exist."""
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setenv("API_PORT", "8011")
    monkeypatch.setenv("PORT", "9999")

    host, port = main._resolve_bind_host_port()

    assert host == "127.0.0.1"
    assert port == 8011


def test_main_rejects_invalid_bind_port(monkeypatch) -> None:
    """Reject non-integer or out-of-range bind ports early."""
    monkeypatch.setenv("API_PORT", "70000")

    try:
        main._resolve_bind_host_port()
    except ValueError as exc:
        assert "between 1 and 65535" in str(exc)
    else:
        raise AssertionError("Expected invalid API_PORT to raise ValueError")


def test_run_ui_pins_cwd_to_repo_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Ensure UI entrypoint helper resets CWD to repository root."""
    monkeypatch.chdir(tmp_path)
    run_ui._ensure_repo_cwd()

    assert Path.cwd() == run_ui._repo_root()


def test_run_ui_resolves_explicit_api_base_url(monkeypatch) -> None:
    """UI entrypoint should honor one explicit API base URL override."""
    monkeypatch.setenv("API_BASE_URL", "http://127.0.0.1:8010/")
    monkeypatch.delenv("UI_API_HOST", raising=False)
    monkeypatch.delenv("UI_API_PORT", raising=False)
    monkeypatch.delenv("API_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)

    assert run_ui._resolve_api_base_url() == "http://127.0.0.1:8010"


def test_run_ui_falls_back_to_ui_host_and_port(monkeypatch) -> None:
    """UI-specific host/port overrides should win over shared API bind vars."""
    monkeypatch.delenv("API_BASE_URL", raising=False)
    monkeypatch.setenv("API_HOST", "10.0.0.20")
    monkeypatch.setenv("API_PORT", "9999")
    monkeypatch.setenv("UI_API_HOST", "localhost")
    monkeypatch.setenv("UI_API_PORT", "8010")
    monkeypatch.delenv("PORT", raising=False)

    assert run_ui._resolve_api_base_url() == "http://localhost:8010"


def test_run_ui_falls_back_to_api_host_and_port(monkeypatch) -> None:
    """Shared API host/port should drive the UI when no UI override exists."""
    monkeypatch.delenv("API_BASE_URL", raising=False)
    monkeypatch.delenv("UI_API_HOST", raising=False)
    monkeypatch.delenv("UI_API_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setenv("API_HOST", "10.0.0.20")
    monkeypatch.setenv("API_PORT", "8011")

    assert run_ui._resolve_api_base_url() == "http://10.0.0.20:8011"


def test_run_ui_maps_wildcard_api_host_to_loopback(monkeypatch) -> None:
    """UI should not try to connect to a wildcard bind address directly."""
    monkeypatch.delenv("API_BASE_URL", raising=False)
    monkeypatch.delenv("UI_API_HOST", raising=False)
    monkeypatch.delenv("UI_API_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setenv("API_HOST", "0.0.0.0")
    monkeypatch.setenv("API_PORT", "8011")

    assert run_ui._resolve_api_base_url() == "http://127.0.0.1:8011"


def test_run_ui_rejects_invalid_api_port(monkeypatch) -> None:
    """Reject invalid UI API ports early in the entrypoint."""
    monkeypatch.delenv("API_BASE_URL", raising=False)
    monkeypatch.setenv("UI_API_PORT", "99999")

    try:
        run_ui._resolve_api_base_url()
    except ValueError as exc:
        assert "between 1 and 65535" in str(exc)
    else:
        raise AssertionError(
            "Expected invalid UI_API_PORT to raise ValueError"
        )
