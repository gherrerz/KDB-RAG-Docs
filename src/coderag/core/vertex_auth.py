"""Helpers to authenticate Vertex AI requests with service accounts."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from google.auth.transport.requests import Request
from google.oauth2 import service_account

from coderag.core.settings import SETTINGS

_VERTEX_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_REFRESH_WINDOW = timedelta(minutes=5)

_credentials_lock = threading.Lock()
_cached_credentials: Optional[service_account.Credentials] = None
_cached_fingerprint: Optional[str] = None


def _fingerprint_secret(raw_json: str) -> str:
    """Return deterministic hash used to invalidate cached credentials."""
    return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()


def _parse_service_account_info(raw_json: str) -> Dict[str, Any]:
    """Parse service account JSON and validate minimum required keys."""
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "VERTEX_SERVICE_ACCOUNT_JSON is not valid JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise RuntimeError(
            "VERTEX_SERVICE_ACCOUNT_JSON must deserialize to an object."
        )

    required_keys = {"client_email", "private_key", "token_uri"}
    missing = sorted(key for key in required_keys if not payload.get(key))
    if missing:
        missing_str = ", ".join(missing)
        raise RuntimeError(
            "VERTEX_SERVICE_ACCOUNT_JSON is missing required keys: "
            f"{missing_str}."
        )

    return payload


def _build_service_account_credentials(
    raw_json: str,
) -> service_account.Credentials:
    """Build credential object with Vertex-compatible OAuth scope."""
    info = _parse_service_account_info(raw_json)
    return service_account.Credentials.from_service_account_info(
        info,
        scopes=[_VERTEX_SCOPE],
    )


def _token_needs_refresh(
    credentials: service_account.Credentials,
) -> bool:
    """Refresh proactively to avoid token expiry mid-request."""
    if credentials.token is None:
        return True
    if credentials.expiry is None:
        return True
    now = datetime.now(timezone.utc)
    expiry = credentials.expiry
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return expiry <= now + _REFRESH_WINDOW


def get_vertex_access_token() -> str:
    """Return an access token for authenticated Vertex API requests."""
    raw_json = SETTINGS.vertex_service_account_json
    if not raw_json:
        raise RuntimeError(
            "VERTEX_SERVICE_ACCOUNT_JSON is required for Vertex provider."
        )

    fingerprint = _fingerprint_secret(raw_json)

    global _cached_credentials
    global _cached_fingerprint

    with _credentials_lock:
        if (
            _cached_credentials is None
            or _cached_fingerprint is None
            or _cached_fingerprint != fingerprint
        ):
            _cached_credentials = _build_service_account_credentials(raw_json)
            _cached_fingerprint = fingerprint

        if _token_needs_refresh(_cached_credentials):
            _cached_credentials.refresh(Request())

        token = _cached_credentials.token

    if not token:
        raise RuntimeError(
            "Unable to obtain Vertex access token from service account."
        )

    return token


def build_vertex_request_headers(
    labels: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Build headers required for Vertex requests plus trace labels."""
    token = get_vertex_access_token()
    headers: Dict[str, str] = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    labels = labels or {}
    for key, value in labels.items():
        suffix = key.replace("_", "-")
        headers[f"X-Vertex-Label-{suffix}"] = value
    return headers


def reset_vertex_credentials_cache() -> None:
    """Reset cache to isolate unit tests that mutate settings values."""
    global _cached_credentials
    global _cached_fingerprint
    with _credentials_lock:
        _cached_credentials = None
        _cached_fingerprint = None
