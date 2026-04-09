"""Embedding generation using configured external provider APIs."""

from __future__ import annotations

from typing import List

import requests

from coderag.core.settings import SETTINGS
from coderag.core.vertex_auth import build_vertex_request_headers

def _embed_text_openai(
    text: str,
    model: str,
) -> List[float]:
    """Generate embeddings using OpenAI embeddings API."""
    if not SETTINGS.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for embeddings.")

    url = f"{SETTINGS.openai_base_url.rstrip('/')}/embeddings"
    headers = {
        "Authorization": f"Bearer {SETTINGS.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "input": text,
    }
    response = requests.post(url, headers=headers, json=payload, timeout=45)
    response.raise_for_status()
    data = response.json()
    items = data.get("data", [])
    if not items:
        raise RuntimeError("OpenAI embeddings response did not include data.")
    values = items[0].get("embedding")
    if not isinstance(values, list) or not values:
        raise RuntimeError("OpenAI embeddings response is missing embedding vector.")
    return [float(v) for v in values]


def _embed_text_gemini(text: str, model: str) -> List[float]:
    """Generate embeddings using Gemini embedContent API."""
    if not SETTINGS.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is required for embeddings.")

    model_name = model if model.startswith("models/") else f"models/{model}"
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"{model_name}:embedContent"
        f"?key={SETTINGS.gemini_api_key}"
    )
    payload = {
        "model": model_name,
        "content": {
            "parts": [{"text": text}],
        },
    }
    response = requests.post(url, json=payload, timeout=45)
    response.raise_for_status()
    data = response.json()
    values = data.get("embedding", {}).get("values")
    if not isinstance(values, list) or not values:
        raise RuntimeError("Gemini embeddings response is missing vector values.")
    return [float(v) for v in values]


def _embed_text_vertex(text: str, model: str) -> List[float]:
    """Generate embeddings using Vertex AI publisher model endpoint."""
    if not SETTINGS.vertex_project_id:
        raise RuntimeError(
            "VERTEX_PROJECT_ID is required for Vertex embeddings."
        )
    try:
        if not SETTINGS.resolve_vertex_service_account_json():
            raise RuntimeError(
                "VERTEX_SERVICE_ACCOUNT_JSON_B64 is required for Vertex "
                "embeddings (or legacy VERTEX_SERVICE_ACCOUNT_JSON)."
            )
    except RuntimeError as exc:
        raise RuntimeError(str(exc)) from exc

    location = SETTINGS.vertex_location
    labels = SETTINGS.resolve_vertex_labels(model_name=model)
    url = (
        f"https://{location}-aiplatform.googleapis.com/v1/projects/"
        f"{SETTINGS.vertex_project_id}/locations/{location}/publishers/google/"
        f"models/{model}:predict"
    )
    payload = {
        "instances": [{"content": text}],
    }
    headers = build_vertex_request_headers(labels)
    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=45,
    )
    response.raise_for_status()
    data = response.json()
    predictions = data.get("predictions", [])
    if not predictions:
        raise RuntimeError("Vertex embeddings response did not include predictions.")

    first = predictions[0]
    values = first.get("embeddings", {}).get("values")
    if values is None:
        values = first.get("values")
    if not isinstance(values, list) or not values:
        raise RuntimeError("Vertex embeddings response is missing vector values.")
    return [float(v) for v in values]


def embed_text(
    text: str,
    size: int = 256,
    provider: str | None = None,
    model: str | None = None,
) -> List[float]:
    """Embed text through configured provider and model without local fallback."""
    _ = size
    effective_provider = SETTINGS.require_embedding_provider_configured(provider)
    effective_model = SETTINGS.resolve_embedding_model(
        provider_override=effective_provider,
        model_override=model,
    )

    try:
        if effective_provider == "openai":
            return _embed_text_openai(text, effective_model)
        if effective_provider == "gemini":
            return _embed_text_gemini(text, effective_model)
        if effective_provider == "vertex":
            return _embed_text_vertex(text, effective_model)
    except requests.RequestException as exc:
        raise RuntimeError(
            "Embedding provider request failed for "
            f"'{effective_provider}' using model '{effective_model}': {exc}"
        ) from exc

    raise RuntimeError(
        "Unsupported embedding provider configured. "
        f"Received: {effective_provider}"
    )
