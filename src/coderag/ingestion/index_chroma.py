"""ChromaDB-backed vector index used in runtime."""

from __future__ import annotations

import base64
import json
import os
import shutil
import stat
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb import errors as chroma_errors

InvalidDimensionException = chroma_errors.InvalidDimensionException
InvalidArgumentError = getattr(chroma_errors, "InvalidArgumentError", ValueError)
InvalidCollectionException = getattr(
    chroma_errors,
    "InvalidCollectionException",
    chroma_errors.NotFoundError,
)

from coderag.core.models import ChunkRecord
from coderag.core.settings import SETTINGS
from coderag.ingestion.embedding import embed_text


def _build_remote_auth_header() -> str | None:
    """Build an optional auth header for remote Chroma connections."""
    token = str(SETTINGS.chroma_token or "").strip()
    if token:
        return f"Bearer {token}"

    username = str(SETTINGS.chroma_username or "").strip()
    password = str(SETTINGS.chroma_password or "").strip()
    if not username or not password:
        return None

    encoded = base64.b64encode(
        f"{username}:{password}".encode("utf-8")
    ).decode("ascii")
    return f"Basic {encoded}"


def _build_remote_chroma_headers() -> dict[str, str]:
    """Return the optional auth headers for a remote Chroma client."""
    auth_header = _build_remote_auth_header()
    if not auth_header:
        return {}
    return {"Authorization": auth_header}


def describe_remote_chroma_target() -> str:
    """Return the sanitized host:port for the configured remote Chroma."""
    host = str(SETTINGS.chroma_host or "").strip() or "<unknown-host>"
    port = int(SETTINGS.chroma_port or 8000)
    return f"{host}:{port}"


def describe_remote_chroma_auth_mode() -> str:
    """Describe the effective auth mode configured for remote Chroma."""
    token = str(SETTINGS.chroma_token or "").strip()
    if token:
        return "bearer"

    username = str(SETTINGS.chroma_username or "").strip()
    password = str(SETTINGS.chroma_password or "").strip()
    if username and password:
        return "basic"
    return "none"


def expected_managed_chroma_hnsw_space() -> str:
    """Return the managed HNSW space configured for the active app."""
    return "cosine"


def get_collection_hnsw_space(collection: Any) -> str | None:
    """Extract the effective HNSW space from collection metadata."""
    metadata = getattr(collection, "metadata", None) or {}
    value = str(metadata.get("hnsw:space") or "").strip().lower()
    return value or None


def _message_contains_any(exc: Exception, patterns: tuple[str, ...]) -> bool:
    """Return whether the normalized exception string contains patterns."""
    message = str(exc).lower()
    return any(pattern in message for pattern in patterns)


def _is_remote_auth_error(exc: Exception) -> bool:
    """Detect authentication failures returned by remote Chroma."""
    return _message_contains_any(
        exc,
        (
            "unauthorized",
            "forbidden",
            "authentication",
            "401",
            "403",
        ),
    )


def _is_remote_timeout_error(exc: Exception) -> bool:
    """Detect timeout failures returned by remote Chroma."""
    return _message_contains_any(exc, ("timeout", "timed out"))


def _is_remote_dns_error(exc: Exception) -> bool:
    """Detect DNS resolution failures for remote Chroma."""
    return _message_contains_any(
        exc,
        (
            "name or service not known",
            "getaddrinfo",
            "temporary failure in name resolution",
            "failed to resolve",
            "nodename nor servname provided",
        ),
    )


def _is_remote_tls_error(exc: Exception) -> bool:
    """Detect TLS failures for remote Chroma."""
    return _message_contains_any(
        exc,
        ("ssl", "tls", "certificate", "cert_verify_failed"),
    )


def _is_remote_unreachable_error(exc: Exception) -> bool:
    """Detect transport-level reachability failures."""
    return _message_contains_any(
        exc,
        (
            "connection refused",
            "couldn't connect",
            "failed to establish a new connection",
            "connection error",
            "network is unreachable",
            "no route to host",
        ),
    )


def _is_remote_proxy_reset_error(exc: Exception) -> bool:
    """Detect resets compatible with proxy or service-mesh failures."""
    return _message_contains_any(
        exc,
        (
            "server disconnected without sending a response",
            "connection reset",
            "connection reset by peer",
            "disconnect/reset before headers",
            "remote protocol error",
            "broken pipe",
        ),
    )


def _is_remote_upstream_restarting_error(exc: Exception) -> bool:
    """Detect errors that usually mean Chroma is restarting."""
    return _message_contains_any(
        exc,
        (
            "503",
            "service unavailable",
            "no healthy upstream",
            "connection aborted",
            "connection closed",
        ),
    )


def _is_remote_payload_too_large_error(exc: Exception) -> bool:
    """Detect payload-too-large failures from remote Chroma."""
    return _message_contains_any(
        exc,
        (
            "payload too large",
            "request entity too large",
            "entity too large",
            "content length exceeded",
            "413",
        ),
    )


def _is_space_mismatch_error(exc: Exception) -> bool:
    """Detect HNSW space mismatches from Chroma exceptions."""
    return _message_contains_any(exc, ("hnsw", "space", "mismatch"))


def detect_remote_chroma_error_signal(exc: Exception) -> str:
    """Classify the most useful operational signal for remote Chroma."""
    if _is_space_mismatch_error(exc):
        return "chroma_hnsw_space_mismatch"
    if _is_remote_auth_error(exc):
        return "chroma_auth_failed"
    if _is_remote_timeout_error(exc):
        return "chroma_timeout"
    if _is_remote_dns_error(exc):
        return "chroma_dns_failed"
    if _is_remote_tls_error(exc):
        return "chroma_tls_failed"
    if _is_remote_payload_too_large_error(exc):
        return "chroma_payload_too_large"
    if _is_remote_proxy_reset_error(exc):
        return "chroma_proxy_reset"
    if _is_remote_upstream_restarting_error(exc):
        return "chroma_upstream_restarting"
    if _is_remote_unreachable_error(exc):
        return "chroma_unreachable"
    return "chroma_unavailable"


def _build_remote_chroma_remediation_hint(signal: str) -> str:
    """Return a short operator hint for one remote Chroma signal."""
    hints = {
        "chroma_auth_failed": (
            "verify CHROMA_TOKEN or CHROMA_USERNAME/CHROMA_PASSWORD"
        ),
        "chroma_timeout": (
            "review network latency, proxy timeouts, and Chroma load"
        ),
        "chroma_dns_failed": (
            "verify CHROMA_HOST and service DNS resolution"
        ),
        "chroma_tls_failed": (
            "review TLS certificates and trust chain"
        ),
        "chroma_payload_too_large": (
            "reduce request batch size before retrying"
        ),
        "chroma_proxy_reset": (
            "review ingress, proxy, or service-mesh resets"
        ),
        "chroma_upstream_restarting": (
            "check remote Chroma availability and pod restarts"
        ),
        "chroma_unreachable": (
            "verify host, port, and network path to Chroma"
        ),
        "chroma_hnsw_space_mismatch": (
            "reset and reingest to realign the managed collection"
        ),
    }
    return hints.get(signal, "")


def build_remote_chroma_error_message(
    *,
    operation: str,
    exc: Exception,
    collection_name: str | None = None,
) -> str:
    """Build a sanitized operational message for remote Chroma failures."""
    signal = detect_remote_chroma_error_signal(exc)
    parts = [
        "remote chroma unavailable",
        f"operation={operation}",
        f"target={describe_remote_chroma_target()}",
        f"auth={describe_remote_chroma_auth_mode()}",
        f"signal={signal}",
    ]
    if collection_name:
        parts.append(f"collection={collection_name}")

    hint = _build_remote_chroma_remediation_hint(signal)
    if hint:
        parts.append(f"hint={hint}")

    parts.append(f"error={exc}")
    return " ".join(parts)


class ChromaVectorIndex:
    """Persistent vector index backed by ChromaDB."""

    def __init__(
        self,
        size: int = 256,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        SETTINGS.require_chroma_enabled()
        self.size = size
        self.embedding_provider = SETTINGS.resolve_embedding_provider(provider)
        self.embedding_model = model or SETTINGS.llm_embedding
        self.embedding_workers = max(1, SETTINGS.ingest_embedding_workers)
        self.upsert_batch_size = max(1, SETTINGS.chroma_upsert_batch_size)
        self.chroma_mode = SETTINGS.chroma_mode
        self._client: Any | None = None
        self._collection: Collection | None = None

    def _build_client(self) -> Any:
        """Build the active Chroma client for the configured runtime mode."""
        if self.chroma_mode == "remote":
            try:
                return chromadb.HttpClient(
                    host=SETTINGS.chroma_host,
                    port=SETTINGS.chroma_port,
                    headers=_build_remote_chroma_headers(),
                )
            except Exception as exc:
                raise RuntimeError(
                    build_remote_chroma_error_message(
                        operation="create_http_client",
                        exc=exc,
                    )
                ) from exc

        raise RuntimeError(
            "Embedded Chroma mode is no longer supported in the Docs "
            "runtime; configure CHROMA_MODE=remote."
        )

    def _ensure_client(self) -> Any:
        """Create the Chroma client lazily when the first operation needs it."""
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _ensure_collection(self) -> Collection:
        """Create the managed collection lazily when first accessed."""
        if self._collection is None:
            self._ensure_client()
            self._collection = self._get_or_create_collection()
        return self._collection

    @staticmethod
    def _on_rmtree_error(func, path, _exc_info) -> None:
        """Retry physical deletion after clearing read-only flags."""
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        func(path)

    @staticmethod
    def _is_chroma_internal_entry(path: Path) -> bool:
        """Keep Chroma-managed files that may stay locked by peers."""
        if path.name.startswith("chroma.sqlite3"):
            return True
        try:
            uuid.UUID(path.name)
            return True
        except ValueError:
            return False

    def _remove_non_chroma_entries(self) -> None:
        """Delete caller-added stale entries without touching live internals."""
        persist_dir = self.persist_dir
        if persist_dir is None or not persist_dir.exists():
            return

        for entry in persist_dir.iterdir():
            if self._is_chroma_internal_entry(entry):
                continue
            if entry.is_dir():
                shutil.rmtree(entry, onerror=self._on_rmtree_error)
            else:
                entry.unlink(missing_ok=True)

    def _get_or_create_collection(self) -> Collection:
        """Return active Chroma collection with cosine distance config."""
        client = self._ensure_client()
        return client.get_or_create_collection(
            name=SETTINGS.chroma_collection,
            metadata={
                "hnsw:space": expected_managed_chroma_hnsw_space(),
            },
        )

    @staticmethod
    def _as_metadata(chunk: ChunkRecord) -> dict[str, object]:
        """Convert chunk to Chroma metadata with primitive values only."""
        return {
            "document_id": chunk.document_id,
            "source_id": chunk.source_id,
            "section_name": chunk.section_name,
            "start_ref": int(chunk.start_ref),
            "end_ref": int(chunk.end_ref),
            "entity_name": chunk.entity_name or "",
            "entity_type": chunk.entity_type or "",
            "extra_metadata": json.dumps(chunk.metadata, ensure_ascii=True),
        }

    @staticmethod
    def _from_record(
        chunk_id: str,
        text: str,
        metadata: dict[str, object],
    ) -> ChunkRecord:
        """Rebuild chunk record from Chroma query payload."""
        raw_extra = metadata.get("extra_metadata", "{}")
        parsed_extra = {}
        if isinstance(raw_extra, str) and raw_extra.strip():
            try:
                parsed_extra = json.loads(raw_extra)
            except json.JSONDecodeError:
                parsed_extra = {}

        return ChunkRecord(
            chunk_id=chunk_id,
            document_id=str(metadata.get("document_id", "")),
            source_id=str(metadata.get("source_id", "")),
            section_name=str(metadata.get("section_name", "")),
            text=text,
            start_ref=int(metadata.get("start_ref", 0)),
            end_ref=int(metadata.get("end_ref", 0)),
            entity_name=str(metadata.get("entity_name") or "") or None,
            entity_type=str(metadata.get("entity_type") or "") or None,
            metadata=parsed_extra if isinstance(parsed_extra, dict) else {},
        )

    def _clear_source(self, source_id: str) -> None:
        """Delete existing vectors belonging to one source."""
        collection = self._ensure_collection()
        try:
            collection.delete(where={"source_id": source_id})
        except InvalidCollectionException:
            # Another process may recreate the collection (e.g. reset).
            self._collection = self._get_or_create_collection()
            self._collection.delete(where={"source_id": source_id})

    def delete_document(self, document_id: str) -> None:
        """Delete all vectors for one document id if they still exist."""
        collection = self._ensure_collection()
        try:
            collection.delete(where={"document_id": document_id})
        except InvalidCollectionException:
            self._collection = self._get_or_create_collection()

    def _embed_chunks(self, chunks: Sequence[ChunkRecord]) -> List[List[float]]:
        """Generate embeddings with bounded parallelism for I/O providers."""
        if not chunks:
            return []
        if len(chunks) == 1 or self.embedding_workers <= 1:
            return [
                embed_text(
                    chunk.text,
                    self.size,
                    provider=self.embedding_provider,
                    model=self.embedding_model,
                )
                for chunk in chunks
            ]

        max_workers = min(self.embedding_workers, len(chunks))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            return list(
                executor.map(
                    lambda chunk: embed_text(
                        chunk.text,
                        self.size,
                        provider=self.embedding_provider,
                        model=self.embedding_model,
                    ),
                    chunks,
                )
            )

    def rebuild(self, chunks: Sequence[ChunkRecord]) -> None:
        """Replace vectors for affected source ids in Chroma collection."""
        if not chunks:
            return

        source_ids = {chunk.source_id for chunk in chunks}
        def _upsert_all() -> None:
            for source_id in source_ids:
                self._clear_source(source_id)

            for start in range(0, len(chunks), self.upsert_batch_size):
                batch = chunks[start:start + self.upsert_batch_size]
                ids = [chunk.chunk_id for chunk in batch]
                documents = [chunk.text for chunk in batch]
                metadatas = [self._as_metadata(chunk) for chunk in batch]
                embeddings = self._embed_chunks(batch)
                self._ensure_collection().upsert(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,
                    embeddings=embeddings,
                )

        try:
            _upsert_all()
        except (
            InvalidDimensionException,
            InvalidArgumentError,
            InvalidCollectionException,
        ):
            # Auto-heal when persisted collection was created with another
            # embedding dimensionality or when a stale collection handle was
            # invalidated by another process.
            try:
                self.clear_all()
                _upsert_all()
            except Exception:
                # On Windows, file locks from another process can temporarily
                # block collection recreation. Keep lexical retrieval available and let the
                # next reset/ingestion retry vector rebuilding.
                return

    def search(
        self,
        query: str,
        top_n: int,
        source_id: Optional[str] = None,
        document_ids: Optional[Sequence[str]] = None,
    ) -> List[Tuple[ChunkRecord, float]]:
        """Search similar chunks in Chroma using query embeddings."""
        if top_n <= 0:
            return []
        allowed_document_ids = {
            document_id
            for document_id in (document_ids or [])
            if document_id
        }
        collection = self._ensure_collection()
        try:
            collection_count = collection.count()
            if collection_count == 0:
                return []
        except InvalidCollectionException:
            self._collection = self._get_or_create_collection()
            collection_count = self._collection.count()
            if collection_count == 0:
                return []

        query_vec = embed_text(
            query,
            self.size,
            provider=self.embedding_provider,
            model=self.embedding_model,
        )
        try:
            params = {
                "query_embeddings": [query_vec],
                "n_results": (
                    collection_count if allowed_document_ids else top_n
                ),
                "include": ["documents", "metadatas", "distances"],
            }
            if source_id:
                params["where"] = {"source_id": source_id}
            payload = self._ensure_collection().query(**params)
        except (
            InvalidDimensionException,
            InvalidArgumentError,
            InvalidCollectionException,
        ):
            return []

        ids = payload.get("ids", [[]])
        documents = payload.get("documents", [[]])
        metadatas = payload.get("metadatas", [[]])
        distances = payload.get("distances", [[]])
        if not ids or not ids[0]:
            return []

        results: List[Tuple[ChunkRecord, float]] = []
        for chunk_id, document, metadata, distance in zip(
            ids[0],
            documents[0],
            metadatas[0],
            distances[0],
        ):
            if not isinstance(metadata, dict):
                continue
            if (
                allowed_document_ids
                and str(metadata.get("document_id", ""))
                not in allowed_document_ids
            ):
                continue
            chunk = self._from_record(
                chunk_id=str(chunk_id),
                text=str(document),
                metadata=metadata,
            )
            score = max(0.0, 1.0 - float(distance))
            results.append((chunk, score))
            if len(results) >= top_n:
                break
        return results

    def clear_all(self) -> None:
        """Reset active vectors without removing locked Chroma internals."""
        client = self._ensure_client()
        try:
            client.delete_collection(name=SETTINGS.chroma_collection)
        except (ValueError, InvalidCollectionException):
            # Chroma raises when the collection is already missing; reset must
            # stay idempotent for API/UI flows.
            pass
        self._collection = self._get_or_create_collection()

    def close(self) -> None:
        """Release client resources held by the current Chroma client."""
        if self._client is None:
            return
        if getattr(self._client, "_closed", False):
            return
        close = getattr(self._client, "close", None)
        if callable(close):
            close()


# Backward compatibility for imports in other modules.
LocalVectorIndex = ChromaVectorIndex
