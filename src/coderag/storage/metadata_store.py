"""SQLite-backed persistence for docs, chunks, graph, and jobs."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from coderag.core.models import (
    ChunkRecord,
    DocumentCatalogEntry,
    DocumentRecord,
    JobStatus,
)


class MetadataStore:
    """Persistence layer used by API and UI workflows."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        # Runtime resets may remove the storage directory while processes are
        # alive. Recreate the directory and retry opening the DB briefly.
        for attempt in range(3):
            db_exists = self.db_path.exists()
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                if not db_exists:
                    self._create_schema(conn)
                return conn
            except sqlite3.OperationalError as exc:
                message = str(exc).lower()
                if "unable to open database file" not in message:
                    raise
                if attempt == 2:
                    raise
                time.sleep(0.05)
        raise RuntimeError("Failed to open SQLite connection")

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            self._create_schema(conn)
        finally:
            conn.close()

    @staticmethod
    def _create_schema(conn: sqlite3.Connection) -> None:
        """Create all tables and indexes required by the metadata store."""
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

            CREATE TABLE IF NOT EXISTS tdm_schemas (
                schema_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                database_name TEXT NOT NULL,
                schema_name TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tdm_tables (
                table_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                schema_id TEXT NOT NULL,
                table_name TEXT NOT NULL,
                table_type TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tdm_columns (
                column_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                table_id TEXT NOT NULL,
                column_name TEXT NOT NULL,
                data_type TEXT NOT NULL,
                nullable INTEGER NOT NULL,
                pii_class TEXT,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tdm_service_mappings (
                mapping_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                service_name TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                method TEXT NOT NULL,
                table_id TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tdm_masking_rules (
                rule_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                rule_name TEXT NOT NULL,
                policy_type TEXT NOT NULL,
                scope TEXT NOT NULL,
                table_id TEXT,
                column_id TEXT,
                priority INTEGER NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tdm_virtualization_artifacts (
                artifact_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                service_name TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                content_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tdm_synthetic_profiles (
                profile_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                profile_name TEXT NOT NULL,
                target_table_id TEXT,
                strategy TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
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

            CREATE INDEX IF NOT EXISTS idx_tdm_schemas_source
            ON tdm_schemas(source_id);

            CREATE INDEX IF NOT EXISTS idx_tdm_tables_source
            ON tdm_tables(source_id);

            CREATE INDEX IF NOT EXISTS idx_tdm_columns_source
            ON tdm_columns(source_id);

            CREATE INDEX IF NOT EXISTS idx_tdm_service_mappings_source
            ON tdm_service_mappings(source_id);

            CREATE INDEX IF NOT EXISTS idx_tdm_masking_rules_source
            ON tdm_masking_rules(source_id);

            CREATE INDEX IF NOT EXISTS idx_tdm_virtualization_artifacts_source
            ON tdm_virtualization_artifacts(source_id);

            CREATE INDEX IF NOT EXISTS idx_tdm_synthetic_profiles_source
            ON tdm_synthetic_profiles(source_id);
            """
        )
        conn.commit()

    @staticmethod
    def _now_iso() -> str:
        """Return UTC timestamp in ISO-8601 format for writes."""
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _json_dump(value: Dict[str, Any]) -> str:
        """Serialize metadata dictionaries with ASCII-safe JSON output."""
        return json.dumps(value, ensure_ascii=True)

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

    def list_documents(
        self,
        source_id: Optional[str] = None,
    ) -> List[DocumentCatalogEntry]:
        """Return lightweight document metadata for UI/API catalog views."""
        conn = self._connect()
        try:
            if source_id:
                rows = conn.execute(
                    """
                    SELECT document_id, source_id, title, path_or_url,
                           content_type, updated_at
                    FROM documents
                    WHERE source_id = ?
                    ORDER BY lower(title) ASC, lower(path_or_url) ASC
                    """,
                    (source_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT document_id, source_id, title, path_or_url,
                           content_type, updated_at
                    FROM documents
                    ORDER BY lower(title) ASC, lower(path_or_url) ASC
                    """
                ).fetchall()
            return [
                DocumentCatalogEntry(
                    document_id=row["document_id"],
                    source_id=row["source_id"],
                    title=row["title"],
                    path_or_url=row["path_or_url"],
                    content_type=row["content_type"],
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
                for row in rows
            ]
        finally:
            conn.close()

    def get_document_by_id(
        self,
        document_id: str,
    ) -> Optional[DocumentCatalogEntry]:
        """Return one persisted document entry by document id."""
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT document_id, source_id, title, path_or_url,
                       content_type, updated_at
                FROM documents
                WHERE document_id = ?
                """,
                (document_id,),
            ).fetchone()
            if row is None:
                return None
            return DocumentCatalogEntry(
                document_id=row["document_id"],
                source_id=row["source_id"],
                title=row["title"],
                path_or_url=row["path_or_url"],
                content_type=row["content_type"],
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
        finally:
            conn.close()

    def find_documents_by_title_and_content_type(
        self,
        title: str,
        content_type: str,
    ) -> List[DocumentCatalogEntry]:
        """Return ingested documents matching title and content type."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT document_id, source_id, title, path_or_url,
                       content_type, updated_at
                FROM documents
                WHERE lower(title) = lower(?)
                  AND lower(content_type) = lower(?)
                ORDER BY updated_at DESC, lower(path_or_url) ASC
                """,
                (title, content_type),
            ).fetchall()
            return [
                DocumentCatalogEntry(
                    document_id=row["document_id"],
                    source_id=row["source_id"],
                    title=row["title"],
                    path_or_url=row["path_or_url"],
                    content_type=row["content_type"],
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                )
                for row in rows
            ]
        finally:
            conn.close()

    def delete_document_by_id(self, document_id: str) -> int:
        """Delete one document row by document id."""
        conn = self._connect()
        try:
            deleted = conn.execute(
                "DELETE FROM documents WHERE document_id = ?",
                (document_id,),
            ).rowcount
            conn.commit()
            return max(0, int(deleted))
        finally:
            conn.close()

    def delete_chunks_by_document_id(self, document_id: str) -> int:
        """Delete all chunk rows belonging to one document id."""
        conn = self._connect()
        try:
            deleted = conn.execute(
                "DELETE FROM chunks WHERE document_id = ?",
                (document_id,),
            ).rowcount
            conn.commit()
            return max(0, int(deleted))
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
            conn.execute("DELETE FROM tdm_schemas")
            conn.execute("DELETE FROM tdm_tables")
            conn.execute("DELETE FROM tdm_columns")
            conn.execute("DELETE FROM tdm_service_mappings")
            conn.execute("DELETE FROM tdm_masking_rules")
            conn.execute("DELETE FROM tdm_virtualization_artifacts")
            conn.execute("DELETE FROM tdm_synthetic_profiles")
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

    def upsert_tdm_schema(
        self,
        schema_id: str,
        source_id: str,
        database_name: str,
        schema_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Insert or update one TDM schema asset."""
        conn = self._connect()
        try:
            now_iso = self._now_iso()
            conn.execute(
                """
                INSERT INTO tdm_schemas (
                    schema_id, source_id, database_name, schema_name,
                    metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(schema_id) DO UPDATE SET
                    source_id = excluded.source_id,
                    database_name = excluded.database_name,
                    schema_name = excluded.schema_name,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at;
                """,
                (
                    schema_id,
                    source_id,
                    database_name,
                    schema_name,
                    self._json_dump(metadata or {}),
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def list_tdm_schemas(
        self,
        source_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return stored TDM schema assets, optionally filtered by source."""
        conn = self._connect()
        try:
            if source_id:
                rows = conn.execute(
                    "SELECT * FROM tdm_schemas WHERE source_id = ?",
                    (source_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM tdm_schemas").fetchall()
            return [
                {
                    "schema_id": row["schema_id"],
                    "source_id": row["source_id"],
                    "database_name": row["database_name"],
                    "schema_name": row["schema_name"],
                    "metadata": json.loads(row["metadata_json"]),
                }
                for row in rows
            ]
        finally:
            conn.close()

    def upsert_tdm_table(
        self,
        table_id: str,
        source_id: str,
        schema_id: str,
        table_name: str,
        table_type: str = "table",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Insert or update one TDM table asset."""
        conn = self._connect()
        try:
            now_iso = self._now_iso()
            conn.execute(
                """
                INSERT INTO tdm_tables (
                    table_id, source_id, schema_id, table_name, table_type,
                    metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(table_id) DO UPDATE SET
                    source_id = excluded.source_id,
                    schema_id = excluded.schema_id,
                    table_name = excluded.table_name,
                    table_type = excluded.table_type,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at;
                """,
                (
                    table_id,
                    source_id,
                    schema_id,
                    table_name,
                    table_type,
                    self._json_dump(metadata or {}),
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def list_tdm_tables(
        self,
        source_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return stored TDM table assets, optionally filtered by source."""
        conn = self._connect()
        try:
            if source_id:
                rows = conn.execute(
                    "SELECT * FROM tdm_tables WHERE source_id = ?",
                    (source_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM tdm_tables").fetchall()
            return [
                {
                    "table_id": row["table_id"],
                    "source_id": row["source_id"],
                    "schema_id": row["schema_id"],
                    "table_name": row["table_name"],
                    "table_type": row["table_type"],
                    "metadata": json.loads(row["metadata_json"]),
                }
                for row in rows
            ]
        finally:
            conn.close()

    def upsert_tdm_column(
        self,
        column_id: str,
        source_id: str,
        table_id: str,
        column_name: str,
        data_type: str,
        nullable: bool = True,
        pii_class: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Insert or update one TDM column asset."""
        conn = self._connect()
        try:
            now_iso = self._now_iso()
            conn.execute(
                """
                INSERT INTO tdm_columns (
                    column_id, source_id, table_id, column_name, data_type,
                    nullable, pii_class, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(column_id) DO UPDATE SET
                    source_id = excluded.source_id,
                    table_id = excluded.table_id,
                    column_name = excluded.column_name,
                    data_type = excluded.data_type,
                    nullable = excluded.nullable,
                    pii_class = excluded.pii_class,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at;
                """,
                (
                    column_id,
                    source_id,
                    table_id,
                    column_name,
                    data_type,
                    1 if nullable else 0,
                    pii_class,
                    self._json_dump(metadata or {}),
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def list_tdm_columns(
        self,
        source_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return stored TDM column assets, optionally filtered by source."""
        conn = self._connect()
        try:
            if source_id:
                rows = conn.execute(
                    "SELECT * FROM tdm_columns WHERE source_id = ?",
                    (source_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM tdm_columns").fetchall()
            return [
                {
                    "column_id": row["column_id"],
                    "source_id": row["source_id"],
                    "table_id": row["table_id"],
                    "column_name": row["column_name"],
                    "data_type": row["data_type"],
                    "nullable": bool(row["nullable"]),
                    "pii_class": row["pii_class"],
                    "metadata": json.loads(row["metadata_json"]),
                }
                for row in rows
            ]
        finally:
            conn.close()

    def upsert_tdm_service_mapping(
        self,
        mapping_id: str,
        source_id: str,
        service_name: str,
        endpoint: str,
        method: str,
        table_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Insert or update one service-to-table mapping for TDM."""
        conn = self._connect()
        try:
            now_iso = self._now_iso()
            conn.execute(
                """
                INSERT INTO tdm_service_mappings (
                    mapping_id, source_id, service_name, endpoint, method,
                    table_id, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mapping_id) DO UPDATE SET
                    source_id = excluded.source_id,
                    service_name = excluded.service_name,
                    endpoint = excluded.endpoint,
                    method = excluded.method,
                    table_id = excluded.table_id,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at;
                """,
                (
                    mapping_id,
                    source_id,
                    service_name,
                    endpoint,
                    method,
                    table_id,
                    self._json_dump(metadata or {}),
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def list_tdm_service_mappings(
        self,
        source_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return stored service mappings, optionally filtered by source."""
        conn = self._connect()
        try:
            if source_id:
                rows = conn.execute(
                    "SELECT * FROM tdm_service_mappings WHERE source_id = ?",
                    (source_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tdm_service_mappings"
                ).fetchall()
            return [
                {
                    "mapping_id": row["mapping_id"],
                    "source_id": row["source_id"],
                    "service_name": row["service_name"],
                    "endpoint": row["endpoint"],
                    "method": row["method"],
                    "table_id": row["table_id"],
                    "metadata": json.loads(row["metadata_json"]),
                }
                for row in rows
            ]
        finally:
            conn.close()

    def upsert_tdm_masking_rule(
        self,
        rule_id: str,
        source_id: str,
        rule_name: str,
        policy_type: str,
        scope: str,
        table_id: Optional[str] = None,
        column_id: Optional[str] = None,
        priority: int = 100,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Insert or update one TDM masking rule."""
        conn = self._connect()
        try:
            now_iso = self._now_iso()
            conn.execute(
                """
                INSERT INTO tdm_masking_rules (
                    rule_id, source_id, rule_name, policy_type, scope,
                    table_id, column_id, priority, metadata_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rule_id) DO UPDATE SET
                    source_id = excluded.source_id,
                    rule_name = excluded.rule_name,
                    policy_type = excluded.policy_type,
                    scope = excluded.scope,
                    table_id = excluded.table_id,
                    column_id = excluded.column_id,
                    priority = excluded.priority,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at;
                """,
                (
                    rule_id,
                    source_id,
                    rule_name,
                    policy_type,
                    scope,
                    table_id,
                    column_id,
                    int(priority),
                    self._json_dump(metadata or {}),
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def list_tdm_masking_rules(
        self,
        source_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return stored masking rules, optionally filtered by source."""
        conn = self._connect()
        try:
            if source_id:
                rows = conn.execute(
                    "SELECT * FROM tdm_masking_rules WHERE source_id = ?",
                    (source_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM tdm_masking_rules").fetchall()
            return [
                {
                    "rule_id": row["rule_id"],
                    "source_id": row["source_id"],
                    "rule_name": row["rule_name"],
                    "policy_type": row["policy_type"],
                    "scope": row["scope"],
                    "table_id": row["table_id"],
                    "column_id": row["column_id"],
                    "priority": int(row["priority"]),
                    "metadata": json.loads(row["metadata_json"]),
                }
                for row in rows
            ]
        finally:
            conn.close()

    def upsert_tdm_virtualization_artifact(
        self,
        artifact_id: str,
        source_id: str,
        service_name: str,
        artifact_type: str,
        content: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Insert or update one virtualization artifact for TDM."""
        conn = self._connect()
        try:
            now_iso = self._now_iso()
            conn.execute(
                """
                INSERT INTO tdm_virtualization_artifacts (
                    artifact_id, source_id, service_name, artifact_type,
                    content_json, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(artifact_id) DO UPDATE SET
                    source_id = excluded.source_id,
                    service_name = excluded.service_name,
                    artifact_type = excluded.artifact_type,
                    content_json = excluded.content_json,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at;
                """,
                (
                    artifact_id,
                    source_id,
                    service_name,
                    artifact_type,
                    self._json_dump(content or {}),
                    self._json_dump(metadata or {}),
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def list_tdm_virtualization_artifacts(
        self,
        source_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return virtualization artifacts, optionally filtered by source."""
        conn = self._connect()
        try:
            if source_id:
                rows = conn.execute(
                    """
                    SELECT * FROM tdm_virtualization_artifacts
                    WHERE source_id = ?
                    """,
                    (source_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tdm_virtualization_artifacts"
                ).fetchall()
            return [
                {
                    "artifact_id": row["artifact_id"],
                    "source_id": row["source_id"],
                    "service_name": row["service_name"],
                    "artifact_type": row["artifact_type"],
                    "content": json.loads(row["content_json"]),
                    "metadata": json.loads(row["metadata_json"]),
                }
                for row in rows
            ]
        finally:
            conn.close()

    def upsert_tdm_synthetic_profile(
        self,
        profile_id: str,
        source_id: str,
        profile_name: str,
        strategy: str = "template",
        target_table_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Insert or update one synthetic data profile for TDM."""
        conn = self._connect()
        try:
            now_iso = self._now_iso()
            conn.execute(
                """
                INSERT INTO tdm_synthetic_profiles (
                    profile_id, source_id, profile_name, target_table_id,
                    strategy, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET
                    source_id = excluded.source_id,
                    profile_name = excluded.profile_name,
                    target_table_id = excluded.target_table_id,
                    strategy = excluded.strategy,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at;
                """,
                (
                    profile_id,
                    source_id,
                    profile_name,
                    target_table_id,
                    strategy,
                    self._json_dump(metadata or {}),
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def list_tdm_synthetic_profiles(
        self,
        source_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return synthetic profiles, optionally filtered by source."""
        conn = self._connect()
        try:
            if source_id:
                rows = conn.execute(
                    "SELECT * FROM tdm_synthetic_profiles WHERE source_id = ?",
                    (source_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tdm_synthetic_profiles"
                ).fetchall()
            return [
                {
                    "profile_id": row["profile_id"],
                    "source_id": row["source_id"],
                    "profile_name": row["profile_name"],
                    "target_table_id": row["target_table_id"],
                    "strategy": row["strategy"],
                    "metadata": json.loads(row["metadata_json"]),
                }
                for row in rows
            ]
        finally:
            conn.close()
