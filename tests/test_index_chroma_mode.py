"""Unit tests for supported remote Chroma client selection."""

from __future__ import annotations

import base64
from pathlib import Path

from coderag.core.settings import SETTINGS
from coderag.ingestion import index_chroma


class _FakeCollection:
    """Minimal Chroma collection stub for client selection tests."""

    def __init__(self, name: str, metadata: dict[str, object]) -> None:
        """Store collection construction arguments for assertions."""
        self.name = name
        self.metadata = metadata


class _FakeClient:
    """Minimal Chroma client stub used for embedded and remote tests."""

    def __init__(self) -> None:
        """Initialize captured collection and delete calls."""
        self.collections: list[tuple[str, dict[str, object]]] = []
        self.deleted: list[str] = []
        self._closed = False

    def get_or_create_collection(
        self,
        name: str,
        metadata: dict[str, object],
    ) -> _FakeCollection:
        """Record collection creation and return a fake collection."""
        self.collections.append((name, metadata))
        return _FakeCollection(name=name, metadata=metadata)

    def delete_collection(self, name: str) -> None:
        """Record collection deletion requests."""
        self.deleted.append(name)

    def close(self) -> None:
        """Record client closure."""
        self._closed = True


def test_index_rejects_embedded_mode_at_runtime(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Embedded mode should fail explicitly in the final Docs runtime."""
    original_mode = SETTINGS.chroma_mode
    original_persist_dir = SETTINGS.chroma_persist_dir
    original_use_chroma = SETTINGS.use_chroma

    def _unexpected_http_client(**kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("HttpClient should not be used in embedded mode")

    monkeypatch.setattr(index_chroma.chromadb, "HttpClient", _unexpected_http_client)

    SETTINGS.use_chroma = True
    SETTINGS.chroma_mode = "embedded"
    SETTINGS.chroma_persist_dir = tmp_path / "chromadb"
    marker_dir = SETTINGS.chroma_persist_dir / "stale"
    marker_dir.mkdir(parents=True)
    marker_file = marker_dir / "marker.txt"
    marker_file.write_text("obsolete", encoding="utf-8")

    index = index_chroma.ChromaVectorIndex(size=8, provider="local", model=None)
    try:
        try:
            index.clear_all()
        except RuntimeError as exc:
            assert "no longer supported" in str(exc)
            assert "CHROMA_MODE=remote" in str(exc)
        else:
            raise AssertionError("Expected embedded mode to be rejected")

        assert marker_file.exists()
    finally:
        index.close()
        SETTINGS.chroma_mode = original_mode
        SETTINGS.chroma_persist_dir = original_persist_dir
        SETTINGS.use_chroma = original_use_chroma


def test_index_uses_remote_http_client_and_skips_local_cleanup(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Remote mode should use HttpClient and avoid local persist-dir cleanup."""
    original_mode = SETTINGS.chroma_mode
    original_persist_dir = SETTINGS.chroma_persist_dir
    original_use_chroma = SETTINGS.use_chroma
    original_collection = SETTINGS.chroma_collection
    original_host = SETTINGS.chroma_host
    original_port = SETTINGS.chroma_port
    original_token = SETTINGS.chroma_token
    original_username = SETTINGS.chroma_username
    original_password = SETTINGS.chroma_password

    captured: dict[str, object] = {}
    client = _FakeClient()
    chroma_dir = tmp_path / "chromadb"
    marker_dir = chroma_dir / "stale"
    marker_dir.mkdir(parents=True)
    marker_file = marker_dir / "marker.txt"
    marker_file.write_text("obsolete", encoding="utf-8")

    def _fake_http_client(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return client

    def _unexpected_persistent_client(**kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError(
            "PersistentClient should not be used in remote mode"
        )

    monkeypatch.setattr(index_chroma.chromadb, "HttpClient", _fake_http_client)
    monkeypatch.setattr(
        index_chroma.chromadb,
        "PersistentClient",
        _unexpected_persistent_client,
    )

    SETTINGS.use_chroma = True
    SETTINGS.chroma_mode = "remote"
    SETTINGS.chroma_persist_dir = chroma_dir
    SETTINGS.chroma_collection = "docs_chunks_remote"
    SETTINGS.chroma_host = "chroma.internal"
    SETTINGS.chroma_port = 9000
    SETTINGS.chroma_token = None
    SETTINGS.chroma_username = "docs-user"
    SETTINGS.chroma_password = "docs-pass"

    index = index_chroma.ChromaVectorIndex(size=8, provider="local", model=None)
    try:
        auth_header = "Basic " + base64.b64encode(
            b"docs-user:docs-pass"
        ).decode("ascii")
        index.clear_all()

        assert captured == {
            "host": "chroma.internal",
            "port": 9000,
            "headers": {"Authorization": auth_header},
        }
        assert marker_file.exists()

        assert client.deleted == ["docs_chunks_remote"]
        assert marker_file.exists()
    finally:
        index.close()
        SETTINGS.chroma_mode = original_mode
        SETTINGS.chroma_persist_dir = original_persist_dir
        SETTINGS.use_chroma = original_use_chroma
        SETTINGS.chroma_collection = original_collection
        SETTINGS.chroma_host = original_host
        SETTINGS.chroma_port = original_port
        SETTINGS.chroma_token = original_token
        SETTINGS.chroma_username = original_username
        SETTINGS.chroma_password = original_password