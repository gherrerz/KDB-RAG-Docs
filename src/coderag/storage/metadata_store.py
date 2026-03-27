"""SQLite-backed persistence for docs, chunks, graph, and jobs."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from coderag.core.models import ChunkRecord, DocumentRecord, JobStatus


class MetadataStore:
    """Persistence layer used by API and UI workflows."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    path_or_url TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    section_name TEXT NOT NULL,
                    text TEXT NOT NULL,
                    start_ref INTEGER NOT NULL,
                    end_ref INTEGER NOT NULL,
                    entity_name TEXT,
                    entity_type TEXT,
                    metadata_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS graph_edges (
                    edge_id TEXT PRIMARY KEY,
                    source_node TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    target_node TEXT NOT NULL,
                    source_id TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS job_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    elapsed_ms REAL NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(job_id, ordinal)
                );

                CREATE TABLE IF NOT EXISTS runtime_state (
                    state_key TEXT PRIMARY KEY,
                    state_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_documents_source
                ON documents(source_id);

                CREATE INDEX IF NOT EXISTS idx_chunks_source
                ON chunks(source_id);

                CREATE INDEX IF NOT EXISTS idx_graph_edges_source
                ON graph_edges(source_id);

                CREATE INDEX IF NOT EXISTS idx_job_events_job
                ON job_events(job_id, ordinal);
                """
            )
            conn.commit()
        finally:
            conn.close()

    def upsert_document(self, doc: DocumentRecord) -> None:
        """Insert or update a document row."""
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO documents (
                    document_id, source_id, title, content, path_or_url,
                    content_type, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    source_id = excluded.source_id,
                    title = excluded.title,
                    content = excluded.content,
                    path_or_url = excluded.path_or_url,
                    content_type = excluded.content_type,
                    updated_at = excluded.updated_at,
                    metadata_json = excluded.metadata_json;
                """,
                (
                    doc.document_id,
                    doc.source_id,
                    doc.title,
                    doc.content,
                    doc.path_or_url,
                    doc.content_type,
                    doc.updated_at.isoformat(),
                    json.dumps(doc.metadata),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def upsert_documents(self, docs: Iterable[DocumentRecord]) -> int:
        """Insert or update many document rows in a single transaction."""
        rows = [
            (
                doc.document_id,
                doc.source_id,
                doc.title,
                doc.content,
                doc.path_or_url,
                doc.content_type,
                doc.updated_at.isoformat(),
                json.dumps(doc.metadata),
            )
            for doc in docs
        ]
        if not rows:
            return 0

        conn = self._connect()
        try:
            conn.executemany(
                """
                INSERT INTO documents (
                    document_id, source_id, title, content, path_or_url,
                    content_type, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    source_id = excluded.source_id,
                    title = excluded.title,
                    content = excluded.content,
                    path_or_url = excluded.path_or_url,
                    content_type = excluded.content_type,
                    updated_at = excluded.updated_at,
                    metadata_json = excluded.metadata_json;
                """,
                rows,
            )
            conn.commit()
            return len(rows)
        finally:
            conn.close()

    def replace_chunks(
        self,
        source_id: str,
        chunks: Iterable[ChunkRecord],
    ) -> None:
        """Replace all chunks for one source with a new list."""
        conn = self._connect()
        try:
            conn.execute(
                "DELETE FROM chunks WHERE source_id = ?",
                (source_id,),
            )
            conn.executemany(
                """
                INSERT INTO chunks (
                    chunk_id, document_id, source_id, section_name,
                    text, start_ref, end_ref, entity_name,
                    entity_type, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        c.chunk_id,
                        c.document_id,
                        c.source_id,
                        c.section_name,
                        c.text,
                        c.start_ref,
                        c.end_ref,
                        c.entity_name,
                        c.entity_type,
                        json.dumps(c.metadata),
                    )
                    for c in chunks
                ],
            )
            conn.commit()
        finally:
            conn.close()

    def list_chunks(
        self,
        source_id: Optional[str] = None,
    ) -> List[ChunkRecord]:
        """Return stored chunks, optionally by source."""
        conn = self._connect()
        try:
            if source_id:
                rows = conn.execute(
                    "SELECT * FROM chunks WHERE source_id = ?",
                    (source_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM chunks").fetchall()
            return [
                ChunkRecord(
                    chunk_id=row["chunk_id"],
                    document_id=row["document_id"],
                    source_id=row["source_id"],
                    section_name=row["section_name"],
                    text=row["text"],
                    start_ref=row["start_ref"],
                    end_ref=row["end_ref"],
                    entity_name=row["entity_name"],
                    entity_type=row["entity_type"],
                    metadata=json.loads(row["metadata_json"]),
                )
                for row in rows
            ]
        finally:
            conn.close()

    def replace_graph_edges(
        self,
        source_id: str,
        edges: Iterable[Tuple[str, str, str, str]],
    ) -> None:
        """Replace graph edges for source with generated edges."""
        conn = self._connect()
        try:
            conn.execute(
                "DELETE FROM graph_edges WHERE source_id = ?",
                (source_id,),
            )
            conn.executemany(
                """
                INSERT INTO graph_edges (
                    edge_id, source_node, relation, target_node, source_id
                ) VALUES (?, ?, ?, ?, ?)
                """,
                list(edges),
            )
            conn.commit()
        finally:
            conn.close()

    def list_graph_edges(
        self,
        source_id: Optional[str] = None,
    ) -> List[Tuple[str, str, str]]:
        """Return graph edges with optional source filter."""
        conn = self._connect()
        try:
            if source_id:
                rows = conn.execute(
                    """
                    SELECT source_node, relation, target_node
                    FROM graph_edges
                    WHERE source_id = ?
                    """,
                    (source_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT source_node, relation, target_node "
                    "FROM graph_edges"
                ).fetchall()
            return [(r[0], r[1], r[2]) for r in rows]
        finally:
            conn.close()

    def upsert_job(self, job: JobStatus) -> None:
        """Insert or update job status."""
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, status, message, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status = excluded.status,
                    message = excluded.message,
                    updated_at = excluded.updated_at;
                """,
                (
                    job.job_id,
                    job.status,
                    job.message,
                    job.created_at.isoformat(),
                    job.updated_at.isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_job(self, job_id: str) -> Optional[JobStatus]:
        """Fetch one job by id."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                return None
            return JobStatus(
                job_id=row["job_id"],
                status=row["status"],
                message=row["message"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
        finally:
            conn.close()

    def touch_job(self, job_id: str, status: str, message: str) -> JobStatus:
        """Convenience helper for quick job updates."""
        now = datetime.now(UTC)
        current = self.get_job(job_id)
        created_at = current.created_at if current else now
        job = JobStatus(
            job_id=job_id,
            status=status,
            message=message,
            created_at=created_at,
            updated_at=now,
        )
        self.upsert_job(job)
        return job

    def append_job_event(
        self,
        job_id: str,
        ordinal: int,
        name: str,
        status: str,
        elapsed_ms: float,
        details: Dict[str, Any],
    ) -> None:
        """Persist one ingestion timeline event for live progress polling."""
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO job_events (
                    job_id, ordinal, name, status, elapsed_ms,
                    details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, ordinal) DO UPDATE SET
                    name = excluded.name,
                    status = excluded.status,
                    elapsed_ms = excluded.elapsed_ms,
                    details_json = excluded.details_json,
                    created_at = excluded.created_at;
                """,
                (
                    job_id,
                    ordinal,
                    name,
                    status,
                    float(elapsed_ms),
                    json.dumps(details, ensure_ascii=True),
                    datetime.now(UTC).isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def list_job_events(self, job_id: str) -> List[Dict[str, Any]]:
        """Return ordered ingestion timeline events for one job."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT ordinal, name, status, elapsed_ms, details_json, created_at
                FROM job_events
                WHERE job_id = ?
                ORDER BY ordinal ASC
                """,
                (job_id,),
            ).fetchall()
            events: List[Dict[str, Any]] = []
            for row in rows:
                raw_details = row["details_json"]
                try:
                    details = json.loads(raw_details)
                except json.JSONDecodeError:
                    details = {}
                if not isinstance(details, dict):
                    details = {}
                events.append(
                    {
                        "ordinal": int(row["ordinal"]),
                        "name": str(row["name"]),
                        "status": str(row["status"]),
                        "elapsed_ms": float(row["elapsed_ms"]),
                        "details": details,
                        "created_at": str(row["created_at"]),
                    }
                )
            return events
        finally:
            conn.close()

    def get_document_map(
        self,
        source_id: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Return quick metadata map by document_id."""
        conn = self._connect()
        try:
            if source_id:
                rows = conn.execute(
                    "SELECT document_id, title, path_or_url FROM documents "
                    "WHERE source_id = ?",
                    (source_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT document_id, title, path_or_url FROM documents"
                ).fetchall()
            return {
                row["document_id"]: {
                    "title": row["title"],
                    "path_or_url": row["path_or_url"],
                }
                for row in rows
            }
        finally:
            conn.close()

    def clear_all_data(self) -> Dict[str, int]:
        """Delete all persisted rows while keeping schema intact."""
        conn = self._connect()
        try:
            deleted_documents = conn.execute(
                "DELETE FROM documents"
            ).rowcount
            deleted_chunks = conn.execute(
                "DELETE FROM chunks"
            ).rowcount
            deleted_graph_edges = conn.execute(
                "DELETE FROM graph_edges"
            ).rowcount
            deleted_jobs = conn.execute(
                "DELETE FROM jobs"
            ).rowcount
            conn.execute("DELETE FROM job_events")
            conn.commit()
            return {
                "deleted_documents": max(0, int(deleted_documents)),
                "deleted_chunks": max(0, int(deleted_chunks)),
                "deleted_graph_edges": max(0, int(deleted_graph_edges)),
                "deleted_jobs": max(0, int(deleted_jobs)),
            }
        finally:
            conn.close()

    def get_runtime_state(self, key: str) -> Optional[str]:
        """Return persisted runtime state value by key."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT state_value FROM runtime_state WHERE state_key = ?",
                (key,),
            ).fetchone()
            if row is None:
                return None
            return str(row["state_value"])
        finally:
            conn.close()

    def set_runtime_state(self, key: str, value: str) -> None:
        """Persist runtime state value by key."""
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO runtime_state (state_key, state_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(state_key) DO UPDATE SET
                    state_value = excluded.state_value,
                    updated_at = excluded.updated_at;
                """,
                (key, value, datetime.now(UTC).isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

    def get_index_version(self) -> int:
        """Return monotonic index version shared across processes."""
        raw_value = self.get_runtime_state("index_version")
        if raw_value is None:
            return 0
        try:
            return int(raw_value)
        except ValueError:
            return 0

    def bump_index_version(self) -> int:
        """Atomically increment and return index version."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT state_value FROM runtime_state WHERE state_key = ?",
                ("index_version",),
            ).fetchone()
            current = 0
            if row is not None:
                try:
                    current = int(str(row["state_value"]))
                except ValueError:
                    current = 0
            next_value = current + 1
            conn.execute(
                """
                INSERT INTO runtime_state (state_key, state_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(state_key) DO UPDATE SET
                    state_value = excluded.state_value,
                    updated_at = excluded.updated_at;
                """,
                (
                    "index_version",
                    str(next_value),
                    datetime.now(UTC).isoformat(),
                ),
            )
            conn.commit()
            return next_value
        finally:
            conn.close()
