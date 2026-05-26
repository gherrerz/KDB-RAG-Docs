"""Tests for readiness diagnostics that now include Chroma runtime state."""

from __future__ import annotations

from fastapi.testclient import TestClient

from coderag.api import server


class _FakeRemoteClient:
    """Minimal remote Chroma client stub for readiness tests."""

    def __init__(
        self,
        *,
        heartbeat_error: Exception | None = None,
        collections: list[object] | None = None,
    ) -> None:
        """Initialize deterministic collection fixtures."""
        self.heartbeat_calls = 0
        self._heartbeat_error = heartbeat_error
        self._collections = collections or ["coderag_chunks", "aux_chunks"]

    def heartbeat(self) -> int:
        """Simulate a successful remote heartbeat."""
        self.heartbeat_calls += 1
        if self._heartbeat_error is not None:
            raise self._heartbeat_error
        return 1

    def list_collections(self) -> list[object]:
        """Return one deterministic list of collection names."""
        return self._collections


class _FakeCollection:
    """Minimal collection stub exposing name and metadata."""

    def __init__(self, name: str, metadata: dict[str, object] | None) -> None:
        """Store collection identity and metadata used by readiness."""
        self.name = name
        self.metadata = metadata or {}


class _FakeVectorIndex:
    """Minimal vector index stub exposing the internals used by readiness."""

    def __init__(
        self,
        client: object,
        *,
        collection: object | None = None,
    ) -> None:
        """Store the fake client returned by _ensure_client()."""
        self._client = client
        self._collection = collection or _FakeCollection(
            "coderag_chunks",
            {"hnsw:space": "cosine"},
        )

    def _ensure_client(self) -> object:
        """Return the injected fake client."""
        return self._client

    def _ensure_collection(self) -> object:
        """Return a minimal fake embedded collection when needed."""
        return self._collection


class _FakeLexicalIndex:
    """Minimal lexical backend stub for readiness checks."""

    backend_label = "lexical"

    def __init__(
        self,
        *,
        ping_error: Exception | None = None,
        snapshot: dict[str, object] | None = None,
    ) -> None:
        self._ping_error = ping_error
        self._snapshot = snapshot or {
            "indexed": True,
            "corpus_rows": 7,
            "document_count": 3,
            "source_count": 2,
        }
        self.ping_calls = 0
        self.health_snapshot_calls = 0

    def ping(self) -> None:
        """Simulate one lexical backend probe."""
        self.ping_calls += 1
        if self._ping_error is not None:
            raise self._ping_error

    def health_snapshot(self) -> dict[str, object]:
        """Return one deterministic lexical corpus snapshot."""
        self.health_snapshot_calls += 1
        return dict(self._snapshot)


def test_ingest_readiness_reports_remote_chroma_details() -> None:
    """Async readiness should surface remote Chroma details in checks."""
    client = TestClient(server.app)
    original_use_rq = server.SETTINGS.use_rq
    original_use_neo4j = server.SETTINGS.use_neo4j
    original_chroma_mode = server.SETTINGS.chroma_mode
    original_chroma_host = server.SETTINGS.chroma_host
    original_chroma_port = server.SETTINGS.chroma_port
    original_chroma_token = server.SETTINGS.chroma_token
    original_chroma_username = server.SETTINGS.chroma_username
    original_chroma_password = server.SETTINGS.chroma_password
    original_vector_index = server.SERVICE.vector_index
    original_lexical_index = server.SERVICE.lexical_index

    fake_client = _FakeRemoteClient()
    fake_lexical = _FakeLexicalIndex()
    server.SETTINGS.use_rq = False
    server.SETTINGS.use_neo4j = False
    server.SETTINGS.chroma_mode = "remote"
    server.SETTINGS.chroma_host = "chroma.internal"
    server.SETTINGS.chroma_port = 9000
    server.SETTINGS.chroma_token = "token-123"
    server.SETTINGS.chroma_username = None
    server.SETTINGS.chroma_password = None
    server.SERVICE.vector_index = _FakeVectorIndex(fake_client)  # type: ignore[assignment]
    server.SERVICE.lexical_index = fake_lexical  # type: ignore[assignment]

    try:
        response = client.get("/sources/ingest/readiness")
    finally:
        server.SETTINGS.use_rq = original_use_rq
        server.SETTINGS.use_neo4j = original_use_neo4j
        server.SETTINGS.chroma_mode = original_chroma_mode
        server.SETTINGS.chroma_host = original_chroma_host
        server.SETTINGS.chroma_port = original_chroma_port
        server.SETTINGS.chroma_token = original_chroma_token
        server.SETTINGS.chroma_username = original_chroma_username
        server.SETTINGS.chroma_password = original_chroma_password
        server.SERVICE.vector_index = original_vector_index  # type: ignore[assignment]
        server.SERVICE.lexical_index = original_lexical_index  # type: ignore[assignment]

    assert response.status_code == 200
    body = response.json()
    chroma_check = body["checks"]["chroma"]
    lexical_check = body["checks"]["lexical"]
    assert body["ready"] is True
    assert lexical_check["ok"] is True
    assert lexical_check["signal"] == "lexical_ready"
    assert lexical_check["backend"] == "lexical"
    assert lexical_check["fts_language"] == server.SETTINGS.lexical_fts_language
    assert lexical_check["target"] == (
        f"{server.SETTINGS.postgres_host}:{server.SETTINGS.postgres_port}"
        f"/{server.SETTINGS.postgres_db}"
    )
    assert lexical_check["indexed"] is True
    assert lexical_check["corpus_rows"] == 7
    assert lexical_check["document_count"] == 3
    assert lexical_check["source_count"] == 2
    assert chroma_check["ok"] is True
    assert chroma_check["signal"] == "chroma_ready"
    assert chroma_check["mode"] == "remote"
    assert chroma_check["target"] == "chroma.internal:9000"
    assert chroma_check["auth_mode"] == "bearer"
    assert chroma_check["collections_count"] == 2
    assert chroma_check["collection"] == "coderag_chunks"
    assert chroma_check["heartbeat_ok"] is True
    assert chroma_check["hnsw_space"] == "cosine"
    assert chroma_check["expected_hnsw_space"] == "cosine"
    assert "target=chroma.internal:9000" in chroma_check["detail"]
    assert "auth=bearer" in chroma_check["detail"]
    assert "collections=2" in chroma_check["detail"]
    assert "collection=coderag_chunks" in chroma_check["detail"]
    assert "hnsw=cosine" in chroma_check["detail"]
    assert "target=" in lexical_check["detail"]
    assert "indexed=true" in lexical_check["detail"]
    assert "corpus_rows=7" in lexical_check["detail"]
    assert fake_client.heartbeat_calls == 1
    assert fake_lexical.ping_calls == 1
    assert fake_lexical.health_snapshot_calls == 1


def test_ingest_readiness_classifies_remote_auth_failure() -> None:
    """Async readiness should return an actionable remote auth signal."""
    client = TestClient(server.app)
    original_use_rq = server.SETTINGS.use_rq
    original_use_neo4j = server.SETTINGS.use_neo4j
    original_chroma_mode = server.SETTINGS.chroma_mode
    original_chroma_host = server.SETTINGS.chroma_host
    original_chroma_port = server.SETTINGS.chroma_port
    original_chroma_token = server.SETTINGS.chroma_token
    original_vector_index = server.SERVICE.vector_index
    original_lexical_index = server.SERVICE.lexical_index

    fake_client = _FakeRemoteClient(
        heartbeat_error=RuntimeError("401 unauthorized"),
    )
    fake_lexical = _FakeLexicalIndex()
    server.SETTINGS.use_rq = False
    server.SETTINGS.use_neo4j = False
    server.SETTINGS.chroma_mode = "remote"
    server.SETTINGS.chroma_host = "chroma.internal"
    server.SETTINGS.chroma_port = 9000
    server.SETTINGS.chroma_token = "token-123"
    server.SERVICE.vector_index = _FakeVectorIndex(fake_client)  # type: ignore[assignment]
    server.SERVICE.lexical_index = fake_lexical  # type: ignore[assignment]

    try:
        response = client.get("/sources/ingest/readiness")
    finally:
        server.SETTINGS.use_rq = original_use_rq
        server.SETTINGS.use_neo4j = original_use_neo4j
        server.SETTINGS.chroma_mode = original_chroma_mode
        server.SETTINGS.chroma_host = original_chroma_host
        server.SETTINGS.chroma_port = original_chroma_port
        server.SETTINGS.chroma_token = original_chroma_token
        server.SERVICE.vector_index = original_vector_index  # type: ignore[assignment]
        server.SERVICE.lexical_index = original_lexical_index  # type: ignore[assignment]

    assert response.status_code == 200
    body = response.json()
    chroma_check = body["checks"]["chroma"]
    assert body["ready"] is False
    assert body["recommendation"] == "sync"
    assert chroma_check["ok"] is False
    assert chroma_check["signal"] == "chroma_auth_failed"
    assert chroma_check["mode"] == "remote"
    assert chroma_check["target"] == "chroma.internal:9000"
    assert chroma_check["auth_mode"] == "bearer"
    assert chroma_check["collection"] == server.SETTINGS.chroma_collection
    assert "signal=chroma_auth_failed" in chroma_check["detail"]
    assert "hint=verify CHROMA_TOKEN" in chroma_check["detail"]


def test_ingest_readiness_detects_hnsw_space_mismatch() -> None:
    """Readiness should fail when the managed collection uses a wrong space."""
    client = TestClient(server.app)
    original_use_rq = server.SETTINGS.use_rq
    original_use_neo4j = server.SETTINGS.use_neo4j
    original_chroma_mode = server.SETTINGS.chroma_mode
    original_vector_index = server.SERVICE.vector_index
    original_lexical_index = server.SERVICE.lexical_index

    fake_client = _FakeRemoteClient()
    mismatched_collection = _FakeCollection(
        "coderag_chunks",
        {"hnsw:space": "l2"},
    )
    fake_lexical = _FakeLexicalIndex()
    server.SETTINGS.use_rq = False
    server.SETTINGS.use_neo4j = False
    server.SETTINGS.chroma_mode = "remote"
    server.SERVICE.vector_index = _FakeVectorIndex(  # type: ignore[assignment]
        fake_client,
        collection=mismatched_collection,
    )
    server.SERVICE.lexical_index = fake_lexical  # type: ignore[assignment]

    try:
        response = client.get("/sources/ingest/readiness")
    finally:
        server.SETTINGS.use_rq = original_use_rq
        server.SETTINGS.use_neo4j = original_use_neo4j
        server.SETTINGS.chroma_mode = original_chroma_mode
        server.SERVICE.vector_index = original_vector_index  # type: ignore[assignment]
        server.SERVICE.lexical_index = original_lexical_index  # type: ignore[assignment]

    assert response.status_code == 200
    body = response.json()
    chroma_check = body["checks"]["chroma"]
    assert body["ready"] is False
    assert chroma_check["ok"] is False
    assert chroma_check["signal"] == "chroma_hnsw_space_mismatch"
    assert chroma_check["mode"] == "remote"
    assert chroma_check["collection"] == "coderag_chunks"
    assert chroma_check["expected_hnsw_space"] == "cosine"
    assert "signal=chroma_hnsw_space_mismatch" in chroma_check["detail"]
    assert "collection=coderag_chunks" in chroma_check["detail"]


def test_ingest_readiness_rejects_embedded_chroma_mode() -> None:
    """Readiness should flag embedded mode as unsupported in the final runtime."""
    client = TestClient(server.app)
    original_use_rq = server.SETTINGS.use_rq
    original_use_neo4j = server.SETTINGS.use_neo4j
    original_chroma_mode = server.SETTINGS.chroma_mode
    original_vector_index = server.SERVICE.vector_index
    original_lexical_index = server.SERVICE.lexical_index

    server.SETTINGS.use_rq = False
    server.SETTINGS.use_neo4j = False
    server.SETTINGS.chroma_mode = "embedded"
    server.SERVICE.vector_index = _FakeVectorIndex(  # type: ignore[assignment]
        object(),
    )
    server.SERVICE.lexical_index = _FakeLexicalIndex()  # type: ignore[assignment]

    try:
        response = client.get("/sources/ingest/readiness")
    finally:
        server.SETTINGS.use_rq = original_use_rq
        server.SETTINGS.use_neo4j = original_use_neo4j
        server.SETTINGS.chroma_mode = original_chroma_mode
        server.SERVICE.vector_index = original_vector_index  # type: ignore[assignment]
        server.SERVICE.lexical_index = original_lexical_index  # type: ignore[assignment]

    assert response.status_code == 200
    body = response.json()
    chroma_check = body["checks"]["chroma"]
    assert body["ready"] is False
    assert body["recommendation"] == "sync"
    assert chroma_check["ok"] is False
    assert chroma_check["signal"] == "chroma_mode_unsupported"
    assert chroma_check["mode"] == "embedded"
    assert chroma_check["collection"] == server.SETTINGS.chroma_collection
    assert "persist_dir" not in chroma_check
    assert "no longer supported" in chroma_check["detail"]


def test_readiness_returns_503_when_chroma_runtime_is_unavailable() -> None:
    """Top-level readiness should fail when the critical Chroma backend fails."""
    client = TestClient(server.app)
    original_chroma_check = server._check_chroma_runtime

    server._check_chroma_runtime = lambda: {  # type: ignore[assignment]
        "required": True,
        "ok": False,
        "detail": "remote chroma unavailable target=chroma.internal:9000",
    }
    try:
        response = client.get("/readiness")
    finally:
        server._check_chroma_runtime = original_chroma_check  # type: ignore[assignment]

    assert response.status_code == 503
    detail = str(response.json().get("detail", ""))
    assert "chroma" in detail.lower()
    assert "chroma.internal:9000" in detail


def test_readiness_returns_503_when_lexical_runtime_is_unavailable() -> None:
    """Top-level readiness should fail when the lexical backend is unavailable."""
    client = TestClient(server.app)
    original_lexical_check = server._check_lexical_runtime

    server._check_lexical_runtime = lambda: {  # type: ignore[assignment]
        "required": True,
        "ok": False,
        "detail": "Postgres lexical backend is unavailable",
    }
    try:
        response = client.get("/readiness")
    finally:
        server._check_lexical_runtime = original_lexical_check  # type: ignore[assignment]

    assert response.status_code == 503
    detail = str(response.json().get("detail", ""))
    assert "lexical" in detail.lower()


def test_ingest_readiness_reports_lexical_probe_failure() -> None:
    """Ingestion readiness should surface lexical backend probe failures."""
    client = TestClient(server.app)
    original_use_rq = server.SETTINGS.use_rq
    original_use_neo4j = server.SETTINGS.use_neo4j
    original_chroma_mode = server.SETTINGS.chroma_mode
    original_vector_index = server.SERVICE.vector_index
    original_lexical_index = server.SERVICE.lexical_index

    server.SETTINGS.use_rq = False
    server.SETTINGS.use_neo4j = False
    server.SETTINGS.chroma_mode = "remote"
    server.SERVICE.vector_index = _FakeVectorIndex(_FakeRemoteClient())  # type: ignore[assignment]
    server.SERVICE.lexical_index = _FakeLexicalIndex(  # type: ignore[assignment]
        ping_error=RuntimeError("relation lexical_corpus does not exist")
    )

    try:
        response = client.get("/sources/ingest/readiness")
    finally:
        server.SETTINGS.use_rq = original_use_rq
        server.SETTINGS.use_neo4j = original_use_neo4j
        server.SETTINGS.chroma_mode = original_chroma_mode
        server.SERVICE.vector_index = original_vector_index  # type: ignore[assignment]
        server.SERVICE.lexical_index = original_lexical_index  # type: ignore[assignment]

    assert response.status_code == 200
    body = response.json()
    lexical_check = body["checks"]["lexical"]
    assert body["ready"] is False
    assert body["recommendation"] == "sync"
    assert lexical_check["ok"] is False
    assert lexical_check["signal"] == "lexical_unreachable"
    assert lexical_check["backend"] == "lexical"
    assert lexical_check["target"] == (
        f"{server.SETTINGS.postgres_host}:{server.SETTINGS.postgres_port}"
        f"/{server.SETTINGS.postgres_db}"
    )
    assert "lexical backend probe failed" in lexical_check["detail"]