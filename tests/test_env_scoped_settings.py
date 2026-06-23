"""Tests for per-environment resolution of infra URLs and credentials.

Verifies the suffix convention ``{VAR}_{SUFFIX}`` -> ``{VAR}`` -> default,
driven by ``RUNTIME_ENVIRONMENT`` (development/test/production), applied to
Chroma, Postgres and Neo4j connection settings and their credentials.
"""

from __future__ import annotations

import pytest

from coderag.core.settings import Settings


def test_scoped_variant_wins_over_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the active env variant exists, it overrides the base var."""
    monkeypatch.setenv("RUNTIME_ENVIRONMENT", "test")
    monkeypatch.setenv("CHROMA_HOST", "base-host")
    monkeypatch.setenv("CHROMA_HOST_TEST", "qa-host")

    assert Settings().chroma_host == "qa-host"


def test_fallback_to_base_when_no_variant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a per-env variant, the base var is used (back-compat)."""
    monkeypatch.setenv("RUNTIME_ENVIRONMENT", "production")
    monkeypatch.setenv("CHROMA_HOST", "base-host")
    monkeypatch.delenv("CHROMA_HOST_PROD", raising=False)

    assert Settings().chroma_host == "base-host"


def test_credentials_are_scoped_per_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User/password/token also resolve from the per-env variant."""
    monkeypatch.setenv("RUNTIME_ENVIRONMENT", "production")
    monkeypatch.setenv("POSTGRES_HOST", "base-host")
    monkeypatch.setenv("POSTGRES_DB", "base-db")
    monkeypatch.setenv("POSTGRES_USER", "base-user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "base-pass")
    monkeypatch.setenv("POSTGRES_HOST_PROD", "pg-prod")
    monkeypatch.setenv("POSTGRES_USER_PROD", "prod-user")
    monkeypatch.setenv("POSTGRES_PASSWORD_PROD", "prod-pass")
    monkeypatch.setenv("POSTGRES_DB_PROD", "prod-db")
    monkeypatch.setenv("NEO4J_PASSWORD_PROD", "prod-neo-pass")

    settings = Settings()

    assert settings.resolve_postgres_dsn() == (
        "postgresql://prod-user:prod-pass@pg-prod:5432/prod-db"
    )
    assert settings.neo4j_password == "prod-neo-pass"


def test_environment_switch_changes_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Switching RUNTIME_ENVIRONMENT selects the matching variant set."""
    monkeypatch.setenv("NEO4J_URI_TEST", "bolt://neo4j-qa:7687")
    monkeypatch.setenv("NEO4J_URI_PROD", "bolt://neo4j-prod:7687")

    monkeypatch.setenv("RUNTIME_ENVIRONMENT", "test")
    assert Settings().neo4j_uri == "bolt://neo4j-qa:7687"

    monkeypatch.setenv("RUNTIME_ENVIRONMENT", "production")
    assert Settings().neo4j_uri == "bolt://neo4j-prod:7687"


def test_non_infra_variables_are_not_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-infra settings ignore the env suffix (stay global)."""
    monkeypatch.setenv("RUNTIME_ENVIRONMENT", "test")
    monkeypatch.setenv("RETRIEVAL_TOP_N", "10")
    monkeypatch.setenv("RETRIEVAL_TOP_N_TEST", "99")

    assert Settings().retrieval_top_n == 10
