"""Tests for the TTL purge script used by ingestion artifacts."""

from __future__ import annotations

import json

import scripts.purge_expired_ingestion_artifacts as purge_script


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
        lambda settings: "postgresql://docs:secret@db.local/docs",
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