"""Tests for provider and embedding model environment resolution."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from coderag.core.settings import Settings


def test_vertex_alias_is_normalized() -> None:
    """Normalize vertex_ai alias to canonical vertex provider."""
    settings = Settings(llm_provider="vertex_ai")
    assert settings.resolve_llm_provider() == "vertex"
    assert settings.resolve_embedding_provider() == "vertex"


def test_embedding_model_global_override_wins() -> None:
    """Prefer LLM_EMBEDDING override over provider-specific defaults."""
    settings = Settings(
        llm_provider="gemini",
        llm_embedding="text-embedding-custom",
        gemini_embedding_model="text-embedding-004",
    )
    assert settings.resolve_embedding_model() == "text-embedding-custom"


def test_embedding_model_uses_provider_default() -> None:
    """Resolve embedding model from selected provider when no override."""
    settings = Settings(
        llm_provider="openai",
        llm_embedding=None,
        openai_embedding_model="text-embedding-3-large",
    )
    assert settings.resolve_embedding_model() == "text-embedding-3-large"


def test_embedding_provider_must_be_external_under_strict_mode() -> None:
    """Reject local provider when embeddings must come from API providers."""
    settings = Settings(llm_provider="local")
    with pytest.raises(RuntimeError):
        settings.require_embedding_provider_configured()


def test_embedding_provider_requires_credentials() -> None:
    """Fail validation when selected provider has no credentials."""
    settings = Settings(llm_provider="openai", openai_api_key=None)
    with pytest.raises(RuntimeError):
        settings.require_embedding_provider_configured()


def test_vertex_provider_requires_service_account_credentials() -> None:
    """Reject Vertex provider when service-account credentials are missing."""
    settings = Settings(
        llm_provider="vertex",
        vertex_project_id="project-id",
        vertex_service_account_json=None,
        vertex_service_account_json_b64=None,
    )
    with pytest.raises(RuntimeError):
        settings.require_embedding_provider_configured()


def test_vertex_provider_is_configured_with_service_account_json() -> None:
    """Accept Vertex provider when project and service account are set."""
    settings = Settings(
        llm_provider="vertex",
        vertex_project_id="project-id",
        vertex_service_account_json=(
            '{"client_email":"svc@test","private_key":"abc",'
            '"token_uri":"https://oauth2.googleapis.com/token"}'
        ),
    )
    assert settings.require_embedding_provider_configured() == "vertex"


def test_vertex_provider_is_configured_with_service_account_json_b64() -> None:
    """Accept Vertex provider when base64 service account payload is set."""
    raw_json = (
        '{"client_email":"svc@test","private_key":"abc",'
        '"token_uri":"https://oauth2.googleapis.com/token"}'
    )
    encoded = base64.b64encode(raw_json.encode("utf-8")).decode("utf-8")
    settings = Settings(
        llm_provider="vertex",
        vertex_project_id="project-id",
        vertex_service_account_json_b64=encoded,
        vertex_service_account_json=None,
    )

    assert settings.require_embedding_provider_configured() == "vertex"
    assert settings.vertex_service_account_json == raw_json
    assert settings.resolve_vertex_service_account_json() == raw_json


def test_vertex_service_account_json_b64_invalid_raises() -> None:
    """Fail clearly when b64 payload cannot be decoded."""
    with pytest.raises(RuntimeError):
        Settings(vertex_service_account_json_b64="not-base64!!")


def test_vertex_labels_defaults_are_available() -> None:
    """Expose default Vertex labels used for request attribution."""
    settings = Settings()
    labels = settings.resolve_vertex_labels()

    assert labels["service"] == "webspec-coipo"
    assert labels["service_account"] == "qa-anthos"
    assert labels["model_name"] == "gemini-2.5-flash"
    assert labels["use_case_id"] == "tbd"


def test_vertex_labels_are_normalized_from_env_values() -> None:
    """Normalize label values to lowercase API-safe tokens."""
    settings = Settings(
        vertex_label_service="Web Spec Coipo",
        vertex_label_service_account="QA Anthos",
        vertex_label_model_name="Gemini 2.0 Flash 001",
        vertex_label_use_case_id="Use Case 01",
    )
    labels = settings.resolve_vertex_labels()

    assert labels["service"] == "web-spec-coipo"
    assert labels["service_account"] == "qa-anthos"
    assert labels["model_name"] == "gemini-2.0-flash-001"
    assert labels["use_case_id"] == "use-case-01"


def test_vertex_labels_use_dynamic_model_override() -> None:
    """Prefer operation model name when resolving Vertex model label."""
    settings = Settings(
        vertex_label_model_name="configured-static-model",
    )

    labels = settings.resolve_vertex_labels(model_name="text-embedding-005")

    assert labels["model_name"] == "text-embedding-005"


def test_chroma_must_be_enabled_in_runtime() -> None:
    """Fail fast when vector runtime is not configured for Chroma."""
    settings = Settings(use_chroma=False)
    with pytest.raises(RuntimeError):
        settings.require_chroma_enabled()


def test_neo4j_must_be_enabled_in_runtime() -> None:
    """Fail fast when graph runtime is not configured for Neo4j."""
    settings = Settings(use_neo4j=False)
    with pytest.raises(RuntimeError):
        settings.require_neo4j_enabled()


def test_relative_paths_are_resolved_to_repo_root() -> None:
    """Resolve default relative paths to absolute repository-root paths."""
    settings = Settings(
        workspace_dir=Path("workspace"),
        data_dir=Path("storage"),
        chroma_persist_dir=Path("storage/chromadb"),
    )
    repo_root = Path(__file__).resolve().parents[1]

    assert settings.workspace_dir == (repo_root / "workspace").resolve()
    assert settings.data_dir == (repo_root / "storage").resolve()
    assert settings.chroma_persist_dir == (
        repo_root / "storage/chromadb"
    ).resolve()


def test_absolute_paths_remain_unchanged(tmp_path: Path) -> None:
    """Keep absolute path values untouched during normalization."""
    workspace_dir = (tmp_path / "workspace").resolve()
    data_dir = (tmp_path / "data").resolve()
    chroma_dir = (tmp_path / "chroma").resolve()

    settings = Settings(
        workspace_dir=workspace_dir,
        data_dir=data_dir,
        chroma_persist_dir=chroma_dir,
    )

    assert settings.workspace_dir == workspace_dir
    assert settings.data_dir == data_dir
    assert settings.chroma_persist_dir == chroma_dir


def test_tdm_flags_default_to_compatibility_mode() -> None:
    """Keep TDM capabilities disabled by default to preserve behavior."""
    settings = Settings()

    assert settings.enable_tdm is False
    assert settings.tdm_enable_masking is False
    assert settings.tdm_enable_virtualization is False
    assert settings.tdm_enable_synthetic is False
    assert settings.tdm_admin_endpoints is False
