# pyright: reportMissingImports=false

"""PostgreSQL-backed operational state helpers for the Docs cutover."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from coderag.core.models import JobStatus
from coderag.storage.postgres_schema import (
    job_events_table,
    jobs_table,
    runtime_state_table,
)
from coderag.storage.postgres_session import PostgresSessionFactory


class PostgresJobStateStore:
    """Persist jobs, job events, and runtime state in PostgreSQL."""

    def __init__(
        self,
        postgres_dsn: str,
        *,
        session_factory: Optional[PostgresSessionFactory] = None,
    ) -> None:
        """Create the store using a reusable SQLAlchemy session factory."""
        self._session_factory = session_factory or PostgresSessionFactory(
            postgres_dsn
        )

    @staticmethod
    def _coerce_details(value: Any) -> dict[str, Any]:
        """Normalize event details to a predictable dictionary shape."""
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str) and value.strip():
            try:
                loaded = json.loads(value)
            except json.JSONDecodeError:
                return {}
            if isinstance(loaded, dict):
                return loaded
        return {}

    def upsert_job(self, job: JobStatus) -> None:
        """Insert or update one persisted job snapshot."""
        insert_stmt = insert(jobs_table).values(
            job_id=job.job_id,
            status=job.status,
            message=job.message,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
        statement = insert_stmt.on_conflict_do_update(
            index_elements=[jobs_table.c.job_id],
            set_={
                "status": insert_stmt.excluded.status,
                "message": insert_stmt.excluded.message,
                "updated_at": insert_stmt.excluded.updated_at,
            },
        )
        with self._session_factory.get_connection() as connection:
            connection.execute(statement)

    def get_job(self, job_id: str) -> Optional[JobStatus]:
        """Fetch one persisted job by id."""
        statement = select(
            jobs_table.c.job_id,
            jobs_table.c.status,
            jobs_table.c.message,
            jobs_table.c.created_at,
            jobs_table.c.updated_at,
        ).where(jobs_table.c.job_id == job_id)
        with self._session_factory.get_connection() as connection:
            row = connection.execute(statement).mappings().one_or_none()
        if row is None:
            return None
        return JobStatus(
            job_id=str(row["job_id"]),
            status=str(row["status"]),
            message=str(row["message"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

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
        details: dict[str, Any],
    ) -> None:
        """Persist one ingestion timeline event for polling and audit."""
        insert_stmt = insert(job_events_table).values(
            job_id=job_id,
            ordinal=int(ordinal),
            name=name,
            status=status,
            elapsed_ms=float(elapsed_ms),
            details_json=dict(details),
            created_at=datetime.now(UTC),
        )
        statement = insert_stmt.on_conflict_do_update(
            index_elements=[job_events_table.c.job_id, job_events_table.c.ordinal],
            set_={
                "name": insert_stmt.excluded.name,
                "status": insert_stmt.excluded.status,
                "elapsed_ms": insert_stmt.excluded.elapsed_ms,
                "details_json": insert_stmt.excluded.details_json,
                "created_at": insert_stmt.excluded.created_at,
            },
        )
        with self._session_factory.get_connection() as connection:
            connection.execute(statement)

    def list_job_events(self, job_id: str) -> list[dict[str, Any]]:
        """Return ordered ingestion timeline events for one job."""
        statement = (
            select(
                job_events_table.c.ordinal,
                job_events_table.c.name,
                job_events_table.c.status,
                job_events_table.c.elapsed_ms,
                job_events_table.c.details_json,
                job_events_table.c.created_at,
            )
            .where(job_events_table.c.job_id == job_id)
            .order_by(job_events_table.c.ordinal.asc())
        )
        with self._session_factory.get_connection() as connection:
            rows = connection.execute(statement).mappings().all()
        return [
            {
                "ordinal": int(row["ordinal"]),
                "name": str(row["name"]),
                "status": str(row["status"]),
                "elapsed_ms": float(row["elapsed_ms"]),
                "details": self._coerce_details(row["details_json"]),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    def clear_jobs(self) -> int:
        """Delete persisted jobs so reset_all remains behaviorally coherent."""
        statement = delete(jobs_table)
        with self._session_factory.get_connection() as connection:
            result = connection.execute(statement)
        return max(0, int(result.rowcount or 0))

    def get_runtime_state(self, key: str) -> Optional[str]:
        """Return one persisted runtime state value by key."""
        statement = select(runtime_state_table.c.state_value).where(
            runtime_state_table.c.state_key == key
        )
        with self._session_factory.get_connection() as connection:
            row = connection.execute(statement).one_or_none()
        if row is None:
            return None
        return str(row[0])

    def set_runtime_state(self, key: str, value: str) -> None:
        """Persist one runtime state value by key."""
        now = datetime.now(UTC)
        insert_stmt = insert(runtime_state_table).values(
            state_key=key,
            state_value=value,
            updated_at=now,
        )
        statement = insert_stmt.on_conflict_do_update(
            index_elements=[runtime_state_table.c.state_key],
            set_={
                "state_value": insert_stmt.excluded.state_value,
                "updated_at": insert_stmt.excluded.updated_at,
            },
        )
        with self._session_factory.get_connection() as connection:
            connection.execute(statement)

    def get_index_version(self) -> int:
        """Return the shared monotonic index version."""
        raw_value = self.get_runtime_state("index_version")
        if raw_value is None:
            return 0
        try:
            return int(raw_value)
        except ValueError:
            return 0

    def bump_index_version(self) -> int:
        """Increment and return the shared index version."""
        statement = select(runtime_state_table.c.state_value).where(
            runtime_state_table.c.state_key == "index_version"
        )
        with self._session_factory.get_connection() as connection:
            row = connection.execute(statement).one_or_none()
            current = 0
            if row is not None:
                try:
                    current = int(str(row[0]))
                except ValueError:
                    current = 0
            next_value = current + 1

            insert_stmt = insert(runtime_state_table).values(
                state_key="index_version",
                state_value=str(next_value),
                updated_at=datetime.now(UTC),
            )
            upsert = insert_stmt.on_conflict_do_update(
                index_elements=[runtime_state_table.c.state_key],
                set_={
                    "state_value": insert_stmt.excluded.state_value,
                    "updated_at": insert_stmt.excluded.updated_at,
                },
            )
            connection.execute(upsert)
        return next_value