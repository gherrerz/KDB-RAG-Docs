"""Tests for Vertex OAuth auth and request label propagation."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta

import pytest

from coderag.core.settings import SETTINGS
from coderag.core.vertex_auth import (
    _token_needs_refresh,
    build_vertex_request_headers,
    get_vertex_access_token,
    reset_vertex_credentials_cache,
)
from coderag.ingestion.embedding import _embed_text_vertex
from coderag.llm.providerlmm_client import ProviderLlmClient


class _FakeGeminiResponse:
    def raise_for_status(self) -> None:
        return

    @staticmethod
    def json() -> dict:
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "respuesta-vertex"}],
                    }
                }
            ]
        }


class _FakeEmbeddingResponse:
    def raise_for_status(self) -> None:
        return

    @staticmethod
    def json() -> dict:
        return {
            "predictions": [
                {
                    "embeddings": {
                        "values": [0.1, 0.2, 0.3],
                    }
                }
            ]
        }


def _set_vertex_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set deterministic Vertex settings values for request tests."""
    raw_json = (
        '{"client_email":"svc@test","private_key":"abc",'
        '"token_uri":"https://oauth2.googleapis.com/token"}'
    )
    encoded_json = base64.b64encode(raw_json.encode("utf-8")).decode(
        "utf-8"
    )
    monkeypatch.setattr(SETTINGS, "vertex_project_id", "project-123")
    monkeypatch.setattr(
        SETTINGS,
        "vertex_service_account_json_b64",
        encoded_json,
    )
    monkeypatch.setattr(
        SETTINGS,
        "vertex_service_account_json",
        None,
    )
    monkeypatch.setattr(SETTINGS, "vertex_location", "us-central1")
    monkeypatch.setattr(
        SETTINGS,
        "vertex_auth_token_url",
        "https://oauth2.googleapis.com/token",
    )
    monkeypatch.setattr(
        SETTINGS,
        "vertex_api_base_url",
        "aiplatform.googleapis.com",
    )
    monkeypatch.setattr(SETTINGS, "vertex_answer_model", "gemini-2.0-flash")
    monkeypatch.setattr(SETTINGS, "vertex_label_service", "webspec-coipo")
    monkeypatch.setattr(
        SETTINGS,
        "vertex_label_service_account",
        "qa-anthos",
    )
    monkeypatch.setattr(
        SETTINGS,
        "vertex_label_model_name",
        "gemini-2.0-flash-001",
    )
    monkeypatch.setattr(SETTINGS, "vertex_label_use_case_id", "tbd")


def test_vertex_answer_uses_bearer_headers_and_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Send Vertex answer calls without API key and with configured labels."""
    _set_vertex_defaults(monkeypatch)
    captured: dict = {}

    def _fake_headers(labels: dict[str, str]) -> dict[str, str]:
        captured["labels_from_headers"] = labels
        return {
            "Authorization": "Bearer fake-token",
            "Content-Type": "application/json",
        }

    def _fake_post(url: str, headers: dict, json: dict, timeout: int):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json
        captured["timeout"] = timeout
        return _FakeGeminiResponse()

    monkeypatch.setattr(
        "coderag.llm.providerlmm_client.build_vertex_request_headers",
        _fake_headers,
    )
    monkeypatch.setattr(
        "coderag.llm.providerlmm_client.requests.post",
        _fake_post,
    )

    output = ProviderLlmClient()._answer_vertex(
        question="Pregunta",
        context="Contexto",
    )

    assert output == "respuesta-vertex"
    assert "?key=" not in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer fake-token"
    expected_labels = SETTINGS.resolve_vertex_labels(
        model_name=SETTINGS.vertex_answer_model,
    )
    assert captured["payload"]["labels"] == expected_labels
    assert captured["labels_from_headers"] == expected_labels


def test_vertex_embedding_uses_bearer_headers_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Send Vertex embedding calls with OAuth headers and no key query."""
    _set_vertex_defaults(monkeypatch)
    captured: dict = {}

    def _fake_headers(labels: dict[str, str]) -> dict[str, str]:
        captured["labels_from_headers"] = labels
        return {
            "Authorization": "Bearer fake-token",
            "Content-Type": "application/json",
            "X-Vertex-Label-service": labels["service"],
        }

    def _fake_post(url: str, headers: dict, json: dict, timeout: int):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json
        captured["timeout"] = timeout
        return _FakeEmbeddingResponse()

    monkeypatch.setattr(
        "coderag.ingestion.embedding.build_vertex_request_headers",
        _fake_headers,
    )
    monkeypatch.setattr(
        "coderag.ingestion.embedding.requests.post",
        _fake_post,
    )

    vector = _embed_text_vertex("hola", "text-embedding-005")

    assert vector == [0.1, 0.2, 0.3]
    assert "?key=" not in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer fake-token"
    expected_labels = SETTINGS.resolve_vertex_labels(
        model_name="text-embedding-005",
    )
    assert captured["labels_from_headers"] == expected_labels


def test_vertex_embedding_uses_configured_api_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Build Vertex embedding URL from configurable base domain."""
    _set_vertex_defaults(monkeypatch)
    monkeypatch.setattr(SETTINGS, "vertex_api_base_url", "alt.example.com")
    captured: dict = {}

    def _fake_headers(labels: dict[str, str]) -> dict[str, str]:
        _ = labels
        return {
            "Authorization": "Bearer fake-token",
            "Content-Type": "application/json",
        }

    def _fake_post(url: str, headers: dict, json: dict, timeout: int):
        captured["url"] = url
        _ = headers, json, timeout
        return _FakeEmbeddingResponse()

    monkeypatch.setattr(
        "coderag.ingestion.embedding.build_vertex_request_headers",
        _fake_headers,
    )
    monkeypatch.setattr(
        "coderag.ingestion.embedding.requests.post",
        _fake_post,
    )

    _embed_text_vertex("hola", "text-embedding-005")

    assert captured["url"].startswith("https://us-central1-alt.example.com")


def test_get_vertex_access_token_uses_configured_token_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use VERTEX_AUTH_TOKEN_URL when building OAuth credentials."""
    _set_vertex_defaults(monkeypatch)
    monkeypatch.setattr(
        SETTINGS,
        "vertex_auth_token_url",
        "https://oauth2-alt.example.com/token",
    )

    captured: dict = {}

    class _FakeCredentials:
        def __init__(self) -> None:
            self.token = None
            self.expiry = None

        def refresh(self, _request) -> None:
            self.token = "token-xyz"

    def _fake_from_service_account_info(info: dict, scopes: list[str]):
        captured["token_uri"] = info.get("token_uri")
        captured["scopes"] = scopes
        return _FakeCredentials()

    monkeypatch.setattr(
        "coderag.core.vertex_auth.service_account.Credentials"
        ".from_service_account_info",
        _fake_from_service_account_info,
    )
    reset_vertex_credentials_cache()

    token = get_vertex_access_token()

    assert token == "token-xyz"
    assert captured["token_uri"] == "https://oauth2-alt.example.com/token"


def test_get_vertex_access_token_requires_service_account_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail fast when service account JSON is not configured."""
    monkeypatch.setattr(SETTINGS, "vertex_service_account_json_b64", None)
    monkeypatch.setattr(SETTINGS, "vertex_service_account_json", None)
    reset_vertex_credentials_cache()

    with pytest.raises(RuntimeError):
        get_vertex_access_token()


def test_build_vertex_request_headers_includes_label_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Map label keys to explicit request headers for observability."""
    monkeypatch.setattr(
        "coderag.core.vertex_auth.get_vertex_access_token",
        lambda: "token-123",
    )

    headers = build_vertex_request_headers(
        {
            "service": "webspec-coipo",
            "service_account": "qa-anthos",
        }
    )

    assert headers["Authorization"] == "Bearer token-123"
    assert headers["X-Vertex-Label-service"] == "webspec-coipo"
    assert headers["X-Vertex-Label-service-account"] == "qa-anthos"


def test_token_refresh_handles_naive_expiry_datetime() -> None:
    """Support credentials implementations that expose naive expiry values."""

    class _FakeCredentials:
        def __init__(self) -> None:
            self.token = "token"
            self.expiry = datetime.utcnow() + timedelta(minutes=10)

    assert _token_needs_refresh(_FakeCredentials()) is False
