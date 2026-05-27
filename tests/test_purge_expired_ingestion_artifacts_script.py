"""Tests for the TTL purge script used by ingestion artifacts."""

from __future__ import annotations

import json
import os

import scripts.purge_expired_ingestion_artifacts as purge_script


def _build_test_postgres_dsn(default_db: str = "coderag_docs") -> str:
    """Build a DSN for tests from env vars without hardcoded credentials."""
    host = os.environ.get("POSTGRES_HOST", "localhost").strip() or "localhost"
    port = os.environ.get("POSTGRES_PORT", "5432").strip() or "5432"
    database = os.environ.get("POSTGRES_DB", default_db).strip() or default_db
    user = os.environ.get("POSTGRES_USER", "").strip()
    password = os.environ.get("POSTGRES_PASSWORD", "").strip()

    if user and password:
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"
    return f"postgresql://{host}:{port}/{database}"


_TEST_POSTGRES_DSN = _build_test_postgres_dsn()


def test_main_returns_error_when_postgres_is_unconfigured(
    monkeypatch,
    capsys,
) -> None:
    """The script should fail fast when Postgres is not configured."""
    monkeypatch.setattr(purge_script, "resolve_postgres_dsn", lambda settings: "")
    monkeypatch.setattr(purge_script.sys, "argv", ["purge_expired_ingestion_artifacts.py"])

    exit_code = purge_script.main()

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "POSTGRES_* no esta configurado" in captured.err


def test_main_runs_ttl_purge_and_prints_json(
    monkeypatch,
    capsys,
) -> None:
    """The script should print the purge count as JSON on success."""
    monkeypatch.setattr(
        purge_script,
        "resolve_postgres_dsn",
        lambda settings: _TEST_POSTGRES_DSN,
    )
    monkeypatch.setattr(
        purge_script,
        "purge_expired_uploaded_artifacts",
        lambda postgres_dsn: 4,
    )
    monkeypatch.setattr(purge_script.sys, "argv", ["purge_expired_ingestion_artifacts.py"])

    exit_code = purge_script.main()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == {"purged_artifacts": 4}